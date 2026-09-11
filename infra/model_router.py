"""Model Router implementing LLMProvider protocol.

Features:
- Cooldown key is strictly (provider, model) tuple.
- Optional fallback to a secondary configured provider on primary cooldown/failure.
- Configurable retry with exponential backoff on 429/timeout.
- Structured logging of fallback activations for observability.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from infra.interfaces import LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class CallRecord:
    """Record of an individual LLM call execution for telemetry and auditing.

    Attributes:
        timestamp: Unix timestamp when the call completed.
        provider: Provider identifier string (e.g. 'groq', 'ollama', 'openrouter').
        model: Specific model identifier.
        prompt_tokens: Number of prompt/input tokens consumed.
        completion_tokens: Number of completion/output tokens generated.
        total_tokens: Total tokens consumed.
        latency_seconds: Duration of the network call in seconds.
        cost_usd: Theoretical commercial Pay-As-You-Go cost in USD.
        status: Execution status ('success' or 'error').
    """

    timestamp: float
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_seconds: float
    cost_usd: float | None
    status: str = "success"


# Commercial Pay-As-You-Go rates (USD per 1 Million tokens: (input_price, output_price))
# Sourced strictly from official rate cards:
# - Groq On-Demand: groq.com/pricing
# - Ollama Cloud: ollama.com/pricing
# - OpenRouter: openrouter.ai/models
# - Cerebras: cerebras.ai
PAY_AS_YOU_GO_RATES: dict[tuple[str, str], tuple[float, float]] = {
    # Groq On-Demand ($ / 1M tokens)
    ("groq", "llama-3.3-70b"): (0.59, 0.79),
    ("groq", "openai/gpt-oss-120b"): (0.35, 0.75),
    ("groq", "gpt-oss-120b"): (0.35, 0.75),
    ("groq", "openai/gpt-oss-20b"): (0.15, 0.35),
    ("groq", "gpt-oss-20b"): (0.15, 0.35),
    ("groq", "qwen/qwen3.8-27b"): (0.60, 3.00),
    ("groq", "qwen3.8-27b"): (0.60, 3.00),
    ("groq", "qwen/qwen3.6-27b"): (0.60, 3.00),
    ("groq", "qwen3.6-27b"): (0.60, 3.00),
    ("groq", "groq/compound"): (0.35, 0.75),
    ("groq", "compound"): (0.35, 0.75),
    ("groq", "mixtral-8x7b-32768"): (0.24, 0.24),
    ("groq", "mixtral-8x7b"): (0.24, 0.24),
    ("groq", "gemma2-9b-it"): (0.20, 0.20),

    # Ollama Cloud ($ / 1M tokens)
    ("ollama", "gpt-oss:120b"): (0.15, 0.60),
    ("ollama", "gpt-oss:120b-cloud"): (0.15, 0.60),
    ("ollama", "nemotron-3-nano:30b"): (0.08, 0.24),
    ("ollama", "nemotron-3-nano:30b-cloud"): (0.08, 0.24),
    ("ollama", "qwen2.5:72b"): (0.35, 1.00),
    ("ollama", "qwen2.5:72b-cloud"): (0.35, 1.00),
    # Ollama Local SLM (Self-hosted on consumer GPU, $0.00 / 1M tokens)
    ("ollama", "qwen2.5:7b-instruct-q4_k_m"): (0.00, 0.00),
    ("ollama", "qwen2.5:7b-instruct"): (0.00, 0.00),
    ("ollama", "qwen2.5:7b"): (0.00, 0.00),
    ("ollama", "qwen2.5:3b-instruct-q4_k_m"): (0.00, 0.00),
    ("ollama", "qwen2.5:3b"): (0.00, 0.00),
    ("ollama", "llama3.2:3b"): (0.00, 0.00),
    ("ollama", "llama3.1:8b"): (0.00, 0.00),
    # OpenRouter ($ / 1M tokens)
    ("openrouter", "meta-llama/llama-3.3-70b-instruct"): (0.10, 0.32),
    ("openrouter", "meta-llama/llama-3.3-70b"): (0.10, 0.32),
    ("openrouter", "meta-llama/llama-3.1-8b-instruct"): (0.03, 0.05),
    ("openrouter", "meta-llama/llama-3.1-8b"): (0.03, 0.05),
    ("openrouter", "qwen/qwen-2.5-72b-instruct"): (0.35, 0.40),
    ("openrouter", "mistralai/mixtral-8x7b-instruct"): (0.24, 0.24),
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"): (0.00, 0.00),
    ("openrouter", "nvidia/nemotron-3.5-lightning:free"): (0.00, 0.00),
    # Cerebras ($ / 1M tokens)
    ("cerebras", "llama-3.3-70b"): (0.60, 0.60),
    ("cerebras", "llama-3.1-8b"): (0.10, 0.10),
}


def calculate_pay_as_you_go_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float | None:
    """Calculate the theoretical commercial Pay-As-You-Go cost in USD for a model call.

    Strictly reflects the actual provider and model that executed the call, including
    when a fallback was activated.
    """
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return 0.0

    p = provider.lower().strip()
    m = model.lower().strip()

    if ":free" in m:
        return 0.0

    rates = PAY_AS_YOU_GO_RATES.get((p, m))

    if rates is None:
        if p == "groq":
            if "8b" in m:
                rates = (0.05, 0.08)
            elif "70b" in m:
                rates = (0.59, 0.79)
            elif "120b" in m or "gpt-oss" in m:
                rates = (0.35, 0.75)
            elif "qwen" in m:
                rates = (0.60, 3.00)
            elif "mixtral" in m:
                rates = (0.24, 0.24)
            else:
                rates = (0.20, 0.40)
        elif p == "ollama":
            if "120b" in m or "gpt-oss" in m:
                rates = (0.15, 0.60)
            elif "nemotron" in m:
                rates = (0.08, 0.24)
            elif "72b" in m:
                rates = (0.35, 1.00)
            elif "8b" in m:
                rates = (0.05, 0.08)
            else:
                rates = (0.0, 0.0)
        elif p == "openrouter":
            if "70b" in m:
                rates = (0.10, 0.32)
            elif "8b" in m:
                rates = (0.03, 0.05)
            elif "72b" in m:
                rates = (0.35, 0.40)
            else:
                rates = (0.15, 0.30)
        elif p == "cerebras":
            if "70b" in m:
                rates = (0.60, 0.60)
            elif "8b" in m:
                rates = (0.10, 0.10)
            else:
                rates = (0.20, 0.20)
        else:
            # Unknown providers/models are valid. Returning None is safer than
            # presenting an invented cost as an accounting fact.
            return None

    input_rate, output_rate = rates
    cost = (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000.0
    return round(cost, 8)


@dataclass
class ProviderConfig:
    """Configuration for an individual model provider endpoint.

    Attributes:
        provider: Provider name ('groq', 'cerebras', 'openrouter').
        model: Model identifier string.
        api_key: Optional API key override (defaults to provider environment variable).
        max_retries: Maximum retry attempts on 429 or timeout.
        base_delay_seconds: Initial backoff delay for exponential backoff.
        timeout_seconds: Network call timeout in seconds.
        extra_params: Additional model parameters.
    """

    provider: str
    model: str
    api_key: str | None = None
    api_base: str | None = None
    protocol: str = "openai-compatible"
    supports_tools: bool = True
    supports_structured_output: bool = False
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    timeout_seconds: float = 60.0
    rate_limiter: Any | None = None
    extra_params: dict[str, Any] = field(default_factory=dict)


class ModelRouter:
    """Intelligent router managing model calls across multiple providers with cooldown and fallback.

    Implements infra.interfaces.LLMProvider protocol.
    """

    def __init__(
        self,
        *,
        providers: list[ProviderConfig],
        fallback: ProviderConfig | None = None,
        client_caller: Callable[..., Any] | None = None,
    ) -> None:
        if not providers:
            raise ValueError("At least one primary provider must be configured.")
        self.providers = providers
        self.fallback = fallback
        self._cooldowns: dict[tuple[str, str], float] = {}
        self._client_caller = client_caller
        self.call_history: list[CallRecord] = []

    def is_in_cooldown(self, *, provider: str, model: str) -> bool:
        """Check if a specific (provider, model) tuple is currently in cooldown."""
        key = (provider, model)
        expire_time = self._cooldowns.get(key)
        if expire_time is None:
            return False
        if time.time() >= expire_time:
            del self._cooldowns[key]
            return False
        return True

    def mark_cooldown(
        self, *, provider: str, model: str, duration_seconds: int = 60
    ) -> None:
        """Put a specific (provider, model) tuple into cooldown for duration_seconds."""
        key = (provider, model)
        self._cooldowns[key] = time.time() + duration_seconds

    async def _invoke_provider(
        self,
        config: ProviderConfig,
        *,
        prompt: str,
        tools: list[dict] | None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        last_exception: Exception | None = None
        estimated_tokens = max(100, len(prompt) // 4 + (max_tokens or 400))

        for attempt in range(config.max_retries):
            # Proactive rate limiting if configured on provider
            if config.rate_limiter is not None and hasattr(config.rate_limiter, "acquire"):
                await config.rate_limiter.acquire(estimated_tokens)

            try:
                if tools and not config.supports_tools:
                    raise RuntimeError(
                        f"Provider/model {config.provider}/{config.model} is configured without tool support"
                    )

                effective_api_key = config.api_key
                if not effective_api_key and config.provider == "ollama" and config.api_base and ("localhost" in config.api_base or "127.0.0.1" in config.api_base):
                    effective_api_key = "ollama"

                if self._client_caller is not None:
                    call_start = time.perf_counter()
                    result = await self._client_caller(
                        provider=config.provider,
                        model=config.model,
                        prompt=prompt,
                        tools=tools,
                        api_key=effective_api_key,
                        api_base=config.api_base,
                        timeout=config.timeout_seconds,
                        max_tokens=max_tokens,
                        **config.extra_params,
                    )
                    call_latency = round(time.perf_counter() - call_start, 4)
                    if isinstance(result, LLMResponse):
                        resp = result
                    else:
                        resp = LLMResponse(
                            content=result.get("content", ""),
                            tool_calls=result.get("tool_calls"),
                            model=config.model,
                            provider=config.provider,
                            usage=result.get("usage"),
                            finish_reason=result.get("finish_reason"),
                            reasoning=result.get("reasoning"),
                        )

                    prompt_toks = (resp.usage or {}).get("prompt_tokens", 0)
                    compl_toks = (resp.usage or {}).get("completion_tokens", 0)
                    tot_toks = (resp.usage or {}).get("total_tokens", prompt_toks + compl_toks)
                    call_cost = calculate_pay_as_you_go_cost(
                        config.provider, config.model, prompt_toks, compl_toks
                    )
                    if resp.latency_seconds == 0.0:
                        resp.latency_seconds = call_latency
                    if resp.cost_usd is None:
                        resp.cost_usd = call_cost

                    self.call_history.append(
                        CallRecord(
                            timestamp=time.time(),
                            provider=config.provider,
                            model=config.model,
                            prompt_tokens=prompt_toks,
                            completion_tokens=compl_toks,
                            total_tokens=tot_toks,
                            latency_seconds=resp.latency_seconds,
                            cost_usd=resp.cost_usd,
                            status="success",
                        )
                    )

                    if (
                        config.rate_limiter is not None
                        and hasattr(config.rate_limiter, "record_usage")
                        and resp.usage
                        and "total_tokens" in resp.usage
                    ):
                        config.rate_limiter.record_usage(
                            estimated_tokens=estimated_tokens,
                            actual_tokens=resp.usage["total_tokens"],
                        )
                    return resp

                # Resolve the configured protocol endpoint. Unknown providers must
                # provide an explicit api_base; never silently route them to Groq.
                api_base = config.api_base
                if not api_base:
                    default_bases = {
                        "groq": "https://api.groq.com/openai/v1",
                        "openrouter": "https://openrouter.ai/api/v1",
                        "cerebras": "https://api.cerebras.ai/v1",
                        "ollama": "http://127.0.0.1:11434/v1",
                        "openai": "https://api.openai.com/v1",
                        "anthropic": "https://api.anthropic.com/v1",
                    }
                    api_base = default_bases.get(config.provider)
                if not api_base:
                    raise RuntimeError(
                        f"Provider '{config.provider}' needs an explicit api_base"
                    )

                base = api_base.rstrip("/")
                if config.protocol.lower() == "anthropic":
                    endpoint_url = (
                        base
                        if base.endswith("/messages")
                        else f"{base}/messages"
                        if base.endswith("/v1")
                        else f"{base}/v1/messages"
                    )
                else:
                    endpoint_url = (
                        base
                        if base.endswith("/chat/completions")
                        else f"{base}/chat/completions"
                        if base.endswith("/v1")
                        else f"{base}/v1/chat/completions"
                    )

                model_name = config.model
                if config.provider == "groq" and model_name.startswith("groq/"):
                    model_name = model_name[len("groq/"):]
                elif config.provider == "openrouter" and model_name.startswith("openrouter/"):
                    model_name = model_name[len("openrouter/"):]
                elif config.provider == "cerebras" and model_name.startswith("cerebras/"):
                    model_name = model_name[len("cerebras/"):]
                elif config.provider == "ollama":
                    if model_name.startswith("ollama/"):
                        model_name = model_name[len("ollama/"):]
                    is_local = api_base and ("localhost" in api_base or "127.0.0.1" in api_base)
                    if api_base and "ollama.com" in api_base:
                        model_name = model_name.replace("-cloud", "")
                    elif is_local and not model_name.endswith("-cloud"):
                        if any(c in model_name for c in ["gpt-oss", "nemotron", "gemma4"]):
                            model_name = f"{model_name}-cloud"

                headers: dict[str, str] = {
                    "Content-Type": "application/json",
                }
                if effective_api_key and config.protocol.lower() == "anthropic":
                    headers["x-api-key"] = effective_api_key
                    headers["anthropic-version"] = "2023-06-01"
                elif effective_api_key:
                    headers["Authorization"] = f"Bearer {effective_api_key}"

                if config.provider == "openrouter":
                    headers["HTTP-Referer"] = "https://github.com/langchain-ai/open_deep_research"
                    headers["X-Title"] = "Deep Research Agent"

                messages = [{"role": "user", "content": prompt}]
                if config.protocol.lower() == "anthropic":
                    payload = {
                        "model": model_name,
                        "messages": messages,
                        "max_tokens": max_tokens
                        or config.extra_params.get("max_tokens", 4096),
                    }
                    if tools:
                        payload["tools"] = [
                            {
                                "name": tool.get("function", {}).get("name", "tool"),
                                "description": tool.get("function", {}).get("description", ""),
                                "input_schema": tool.get("function", {}).get(
                                    "parameters", {"type": "object"}
                                ),
                            }
                            for tool in tools
                        ]
                else:
                    payload = {
                        "model": model_name,
                        "messages": messages,
                    }
                    if max_tokens is not None:
                        payload["max_tokens"] = max_tokens
                    elif "max_tokens" in config.extra_params:
                        payload["max_tokens"] = config.extra_params["max_tokens"]

                    if tools:
                        payload["tools"] = tools

                # Pass extra parameters (excluding max_tokens which is handled above)
                for k, v in config.extra_params.items():
                    if k not in payload and k != "max_tokens":
                        payload[k] = v

                # API-native reasoning & provider options
                if config.protocol.lower() != "anthropic" and config.provider == "groq":
                    if "reasoning_format" not in payload:
                        payload["reasoning_format"] = "parsed"
                elif config.provider == "openrouter":
                    if "reasoning" not in payload and "reasoning_effort" not in payload:
                        payload["reasoning"] = {"exclude": True}
                elif config.provider == "ollama":
                    is_local = api_base and ("localhost" in api_base or "127.0.0.1" in api_base)
                    if is_local:
                        options = payload.setdefault("options", {})
                        options.setdefault("num_ctx", config.extra_params.get("num_ctx", 16384))
                        options.setdefault("temperature", config.extra_params.get("temperature", 0.2))
                        options.setdefault("repeat_penalty", config.extra_params.get("repeat_penalty", 1.05))

                call_start = time.perf_counter()
                async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
                    http_resp = await client.post(endpoint_url, json=payload, headers=headers)
                call_latency = round(time.perf_counter() - call_start, 4)

                if http_resp.status_code == 429:
                    retry_after = http_resp.headers.get("retry-after")
                    reset_tokens = http_resp.headers.get("x-ratelimit-reset-tokens")
                    reset_requests = http_resp.headers.get("x-ratelimit-reset-requests")
                    resp_text = http_resp.text

                    dynamic_wait = None
                    if retry_after:
                        try:
                            dynamic_wait = float(retry_after)
                        except ValueError:
                            pass
                    if dynamic_wait is None and reset_tokens:
                        try:
                            clean_val = reset_tokens.rstrip("s").strip()
                            if clean_val.endswith("ms"):
                                dynamic_wait = float(clean_val[:-2]) / 1000.0
                            else:
                                dynamic_wait = float(clean_val)
                        except ValueError:
                            pass
                    if dynamic_wait is None and reset_requests:
                        try:
                            clean_val = reset_requests.rstrip("s").strip()
                            if clean_val.endswith("ms"):
                                dynamic_wait = float(clean_val[:-2]) / 1000.0
                            else:
                                dynamic_wait = float(clean_val)
                        except ValueError:
                            pass
                    if dynamic_wait is None:
                        match = re.search(r"try again in ([\d\.]+)s", resp_text, re.IGNORECASE)
                        if match:
                            dynamic_wait = float(match.group(1))

                    cooldown_duration = int(dynamic_wait) + 2 if dynamic_wait else 60
                    self.mark_cooldown(
                        provider=config.provider,
                        model=config.model,
                        duration_seconds=cooldown_duration,
                    )
                    raise RuntimeError(
                        f"HTTP 429 Rate limit from {config.provider}/{config.model} (try again in {cooldown_duration}s): {resp_text}"
                    )

                if http_resp.status_code >= 400:
                    # Defensive Recovery for Groq "tool_use_failed" error:
                    # Groq server-side parser aborts with HTTP 400 if model emits bare tool call JSON
                    # when tools weren't in request body, BUT Groq includes the complete generated text
                    # in error.failed_generation! Recover it rather than failing.
                    if http_resp.status_code == 400 and config.provider == "groq":
                        try:
                            err_data = http_resp.json()
                            err_obj = err_data.get("error", {})
                            if err_obj.get("code") == "tool_use_failed" and "failed_generation" in err_obj:
                                recovered_gen = err_obj["failed_generation"]
                                logger.info(
                                    "Defensively recovered %d chars from Groq tool_use_failed on %s",
                                    len(recovered_gen),
                                    config.model,
                                )
                                comp_toks = max(10, len(recovered_gen) // 4)
                                cost = calculate_pay_as_you_go_cost(
                                    config.provider, config.model, estimated_tokens, comp_toks
                                )
                                return LLMResponse(
                                    content=recovered_gen,
                                    model=config.model,
                                    provider=config.provider,
                                    usage={
                                        "prompt_tokens": estimated_tokens,
                                        "completion_tokens": comp_toks,
                                        "total_tokens": estimated_tokens + comp_toks,
                                    },
                                    finish_reason="stop",
                                    latency_seconds=call_latency,
                                    cost_usd=cost,
                                )
                        except Exception:
                            pass

                    raise RuntimeError(
                        f"HTTP {http_resp.status_code} from {config.provider}/{config.model}: {http_resp.text}"
                    )

                data = http_resp.json()
                if config.protocol.lower() == "anthropic":
                    content_blocks = data.get("content") or []
                    content = "".join(
                        block.get("text", "")
                        for block in content_blocks
                        if block.get("type") == "text"
                    )
                    tool_blocks = [
                        block for block in content_blocks if block.get("type") == "tool_use"
                    ]
                    tool_calls = [
                        {
                            "id": block.get("id"),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        }
                        for block in tool_blocks
                    ] or None
                    finish_reason = data.get("stop_reason")
                    reasoning = None
                    usage_data = data.get("usage") or {}
                    usage_dict = {
                        "prompt_tokens": usage_data.get("input_tokens", 0),
                        "completion_tokens": usage_data.get("output_tokens", 0),
                    }
                    usage_dict["total_tokens"] = (
                        usage_dict["prompt_tokens"] + usage_dict["completion_tokens"]
                    )
                else:
                    choices = data.get("choices") or []
                    if not choices:
                        raise RuntimeError(
                            f"Empty choices returned from {config.provider}/{config.model}: {data}"
                        )

                    choice = choices[0]
                    message = choice.get("message") or {}
                    content = message.get("content") or ""
                    finish_reason = choice.get("finish_reason")

                    # Extract separated reasoning tokens if emitted by the provider
                    reasoning = message.get("reasoning") or message.get("reasoning_content")
                    if isinstance(reasoning, str):
                        reasoning = reasoning.strip() or None

                    tool_calls = message.get("tool_calls")
                    if tool_calls and isinstance(tool_calls, list):
                        tool_calls = [
                            tc if isinstance(tc, dict) else (tc.model_dump() if hasattr(tc, "model_dump") else dict(tc))
                            for tc in tool_calls
                        ]
                    else:
                        tool_calls = None

                    usage_dict = data.get("usage")

                # Defensive recovery: If model produced empty content but generated substantive reasoning
                # (e.g. Qwen/DeepSeek reasoning models hitting token limits during thinking),
                # promote reasoning to content so downstream nodes never receive an empty text.
                if not content.strip() and reasoning and len(reasoning.strip()) > 30:
                    logger.warning(
                        "Model (%s, %s) produced empty content with %d chars of reasoning; promoting reasoning to content.",
                        config.provider,
                        config.model,
                        len(reasoning),
                    )
                    content = reasoning

                if (
                    config.rate_limiter is not None
                    and hasattr(config.rate_limiter, "record_usage")
                    and usage_dict
                    and "total_tokens" in usage_dict
                ):
                    config.rate_limiter.record_usage(
                        estimated_tokens=estimated_tokens,
                        actual_tokens=usage_dict["total_tokens"],
                    )

                prompt_toks = usage_dict.get("prompt_tokens", 0) if usage_dict else 0
                compl_toks = usage_dict.get("completion_tokens", 0) if usage_dict else 0
                tot_toks = usage_dict.get("total_tokens", prompt_toks + compl_toks) if usage_dict else 0
                call_cost = calculate_pay_as_you_go_cost(
                    config.provider, config.model, prompt_toks, compl_toks
                )

                self.call_history.append(
                    CallRecord(
                        timestamp=time.time(),
                        provider=config.provider,
                        model=config.model,
                        prompt_tokens=prompt_toks,
                        completion_tokens=compl_toks,
                        total_tokens=tot_toks,
                        latency_seconds=call_latency,
                        cost_usd=call_cost,
                        status="success",
                    )
                )

                return LLMResponse(
                    content=content,
                    tool_calls=tool_calls,
                    model=config.model,
                    provider=config.provider,
                    usage=usage_dict,
                    finish_reason=finish_reason,
                    reasoning=reasoning,
                    latency_seconds=call_latency,
                    cost_usd=call_cost,
                )

            except Exception as exc:
                last_exception = exc
                err_msg = str(exc).lower()
                is_rate_limit_or_timeout = (
                    "429" in err_msg or "rate limit" in err_msg or "timeout" in err_msg
                )

                # Header-aware dynamic retry delay extraction
                match = re.search(r"try again in ([\d\.]+)s", str(exc), re.IGNORECASE)
                dynamic_wait = float(match.group(1)) if match else None
                cooldown_duration = int(dynamic_wait) + 2 if dynamic_wait else 60

                if is_rate_limit_or_timeout:
                    self.mark_cooldown(
                        provider=config.provider,
                        model=config.model,
                        duration_seconds=cooldown_duration,
                    )

                if attempt < config.max_retries - 1:
                    # If dynamic wait is short (<= 10s), wait directly; otherwise backoff exponentially
                    if dynamic_wait is not None and dynamic_wait <= 10.0:
                        delay = dynamic_wait + 0.5
                    else:
                        delay = config.base_delay_seconds * (2**attempt)
                    await asyncio.sleep(delay)
                else:
                    break

        raise last_exception or RuntimeError(
            f"Failed to execute completion on {config.provider}/{config.model}"
        )

    async def complete(
        self,
        *,
        prompt: str,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Complete prompt by querying primary providers, falling back to secondary provider if needed."""
        last_error: Exception | None = None

        for provider_cfg in self.providers:
            if self.is_in_cooldown(
                provider=provider_cfg.provider, model=provider_cfg.model
            ):
                logger.info(
                    "Provider (%s, %s) is in cooldown. Skipping.",
                    provider_cfg.provider,
                    provider_cfg.model,
                )
                continue

            try:
                return await self._invoke_provider(
                    provider_cfg, prompt=prompt, tools=tools, max_tokens=max_tokens
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Primary provider (%s, %s) failed after retries: %s",
                    provider_cfg.provider,
                    provider_cfg.model,
                    exc,
                )

        primary_summary = ", ".join(
            f"({p.provider}, {p.model})" for p in self.providers
        )
        reason = (
            str(last_error) if last_error else "All primary providers are in cooldown"
        )
        if self.fallback is None:
            raise last_error or RuntimeError(
                f"All configured providers failed or are in cooldown: {primary_summary}"
            )

        logger.warning(
            "Fallback activated: primary providers [%s] unavailable (reason: %s). Routing to fallback (%s, %s)",
            primary_summary,
            reason,
            self.fallback.provider,
            self.fallback.model,
        )

        return await self._invoke_provider(
            self.fallback, prompt=prompt, tools=tools, max_tokens=max_tokens
        )

    def get_telemetry_summary(self) -> dict[str, Any]:
        """Return aggregated telemetry metrics across all model calls."""
        total_calls = len(self.call_history)
        total_latency = sum(r.latency_seconds for r in self.call_history)
        total_prompt_tokens = sum(r.prompt_tokens for r in self.call_history)
        total_completion_tokens = sum(r.completion_tokens for r in self.call_history)
        total_tokens = sum(r.total_tokens for r in self.call_history)
        known_costs = [r.cost_usd for r in self.call_history if r.cost_usd is not None]
        total_cost_usd = sum(known_costs)
        unknown_cost_calls = len(self.call_history) - len(known_costs)

        by_model: dict[str, dict[str, Any]] = {}
        for r in self.call_history:
            key = f"{r.provider}/{r.model}"
            if key not in by_model:
                by_model[key] = {
                    "calls": 0,
                    "latency_seconds": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                    "cost_known": True,
                }
            entry = by_model[key]
            entry["calls"] += 1
            entry["latency_seconds"] += r.latency_seconds
            entry["prompt_tokens"] += r.prompt_tokens
            entry["completion_tokens"] += r.completion_tokens
            entry["total_tokens"] += r.total_tokens
            if r.cost_usd is None:
                entry["cost_known"] = False
            else:
                entry["cost_usd"] += r.cost_usd

        for entry in by_model.values():
            entry["latency_seconds"] = round(entry["latency_seconds"], 4)
            entry["cost_usd"] = round(entry["cost_usd"], 6)

        return {
            "total_calls": total_calls,
            "total_latency_seconds": round(total_latency, 4),
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost_usd, 6),
            "unknown_cost_calls": unknown_cost_calls,
            "by_model": by_model,
            "call_history": list(self.call_history),
        }

    def reset_telemetry(self) -> None:
        """Clear recorded call history and reset metrics."""
        self.call_history.clear()
