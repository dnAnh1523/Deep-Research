"""Tests for infra.model_router."""

import asyncio
import logging
import pytest
from infra.interfaces import LLMProvider, LLMResponse
from infra.model_router import ModelRouter, ProviderConfig


def test_model_router_conforms_to_llm_provider():
    primary = ProviderConfig(provider="groq", model="llama-3.3-70b")
    fallback = ProviderConfig(provider="openrouter", model="meta-llama/llama-3.3-70b")
    router = ModelRouter(providers=[primary], fallback=fallback)
    assert isinstance(router, LLMProvider)


def test_cooldown_key_is_strictly_provider_model_tuple():
    primary1 = ProviderConfig(provider="groq", model="llama-3.3-70b")
    primary2 = ProviderConfig(provider="groq", model="mixtral-8x7b")
    fallback = ProviderConfig(provider="openrouter", model="meta-llama/llama-3.3-70b")
    router = ModelRouter(providers=[primary1, primary2], fallback=fallback)

    assert not router.is_in_cooldown(provider="groq", model="llama-3.3-70b")
    assert not router.is_in_cooldown(provider="groq", model="mixtral-8x7b")

    # Cooldown only the first model
    router.mark_cooldown(provider="groq", model="llama-3.3-70b", duration_seconds=60)

    assert router.is_in_cooldown(provider="groq", model="llama-3.3-70b")
    # Crucial assertion: other model of same provider MUST NOT be in cooldown!
    assert not router.is_in_cooldown(provider="groq", model="mixtral-8x7b")


def test_automatic_fallback_when_primary_in_cooldown(caplog):
    async def run():
        primary = ProviderConfig(provider="groq", model="llama-3.3-70b")
        fallback = ProviderConfig(provider="openrouter", model="meta-llama/llama-3.3-70b")

        async def mock_caller(provider: str, model: str, prompt: str, **kwargs):
            return LLMResponse(content=f"Response from {provider}:{model}")

        router = ModelRouter(providers=[primary], fallback=fallback, client_caller=mock_caller)

        # Primary in cooldown
        router.mark_cooldown(provider="groq", model="llama-3.3-70b", duration_seconds=100)

        with caplog.at_level(logging.WARNING):
            response = await router.complete(prompt="Summarize quantum computing")

        assert response.content == "Response from openrouter:meta-llama/llama-3.3-70b"
        assert "Fallback activated" in caplog.text
        assert "groq" in caplog.text
        assert "openrouter" in caplog.text

    asyncio.run(run())


def test_retry_with_exponential_backoff_and_cooldown_on_429():
    async def run():
        attempts = 0
        sleeps = []

        async def mock_sleep(seconds: float):
            sleeps.append(seconds)

        async def mock_caller(provider: str, model: str, prompt: str, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("Rate limit reached 429 Too Many Requests")
            return LLMResponse(content="Success after retry")

        original_sleep = asyncio.sleep
        asyncio.sleep = mock_sleep

        try:
            primary = ProviderConfig(
                provider="groq",
                model="llama-3.3-70b",
                max_retries=3,
                base_delay_seconds=0.5,
            )
            fallback = ProviderConfig(provider="openrouter", model="fallback-model")
            router = ModelRouter(providers=[primary], fallback=fallback, client_caller=mock_caller)

            response = await router.complete(prompt="Hello")
            assert response.content == "Success after retry"
            assert attempts == 3
            # Exponential backoff delays: base * 2^0 = 0.5, base * 2^1 = 1.0
            assert sleeps == [0.5, 1.0]
            # Since 429 happened, router marked it in cooldown
            assert router.is_in_cooldown(provider="groq", model="llama-3.3-70b")
        finally:
            asyncio.sleep = original_sleep

    asyncio.run(run())


def test_all_providers_fail_raises_exception():
    async def run():
        async def mock_failing_caller(provider: str, model: str, **kwargs):
            raise RuntimeError(f"Endpoint down for {provider}")

        primary = ProviderConfig(provider="groq", model="llama-3.3-70b", max_retries=1)
        fallback = ProviderConfig(provider="openrouter", model="fallback-model", max_retries=1)
        router = ModelRouter(providers=[primary], fallback=fallback, client_caller=mock_failing_caller)

        with pytest.raises(RuntimeError, match="Endpoint down for openrouter"):
            await router.complete(prompt="Should fail completely")

    asyncio.run(run())


def test_model_router_extracts_reasoning_and_keeps_content_clean():
    """Verify that reasoning tokens are cleanly extracted into LLMResponse.reasoning."""
    async def run():
        captured_kwargs = {}

        async def mock_reasoning_caller(provider: str, model: str, prompt: str, **kwargs):
            captured_kwargs.update(kwargs)
            return LLMResponse(
                content="# Báo cáo Tổng hợp\n\nNội dung chính sạch.",
                reasoning="Internal thinking trace...",
                model=model,
                provider=provider,
            )

        primary = ProviderConfig(
            provider="groq",
            model="qwen/qwen3.6-27b",
            extra_params={"reasoning_format": "parsed"},
        )
        fallback = ProviderConfig(provider="openrouter", model="meta-llama/llama-3.3-70b")
        router = ModelRouter(providers=[primary], fallback=fallback, client_caller=mock_reasoning_caller)

        response = await router.complete(prompt="Phân tích thị trường")

        assert response.content == "# Báo cáo Tổng hợp\n\nNội dung chính sạch."
        assert response.reasoning == "Internal thinking trace..."
        assert "<think>" not in response.content
        assert captured_kwargs.get("reasoning_format") == "parsed"

    asyncio.run(run())


def test_model_router_supports_ollama_provider():
    """Verify that ModelRouter correctly configures and routes Ollama Cloud/Local endpoints."""
    async def run():
        captured_kwargs = {}

        async def mock_ollama_caller(provider: str, model: str, prompt: str, **kwargs):
            captured_kwargs.update(kwargs)
            return LLMResponse(
                content="Response from Ollama",
                model=model,
                provider=provider,
            )

        ollama_cfg = ProviderConfig(
            provider="ollama",
            model="gpt-oss:120b",
            api_key="mock_ollama_key",
            api_base="https://ollama.com/v1",
        )
        fallback = ProviderConfig(provider="openrouter", model="meta-llama/llama-3.3-70b")
        router = ModelRouter(providers=[ollama_cfg], fallback=fallback, client_caller=mock_ollama_caller)

        response = await router.complete(prompt="Test prompt")

        assert response.content == "Response from Ollama"
        assert response.provider == "ollama"
        assert captured_kwargs.get("api_base") == "https://ollama.com/v1"
        assert captured_kwargs.get("api_key") == "mock_ollama_key"

    asyncio.run(run())


def test_model_router_tracks_latency_and_cost_per_call():
    """Verify that every LLM call accurately tracks latency and Pay-As-You-Go cost."""
    async def run():
        async def mock_caller(provider: str, model: str, prompt: str, **kwargs):
            await asyncio.sleep(0.01)  # simulate network latency
            return LLMResponse(
                content="Llama 3.1 8B Response",
                model=model,
                provider=provider,
                usage={"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
            )

        primary = ProviderConfig(provider="groq", model="openai/gpt-oss-120b")
        fallback = ProviderConfig(provider="openrouter", model="meta-llama/llama-3.1-8b-instruct")
        router = ModelRouter(providers=[primary], fallback=fallback, client_caller=mock_caller)

        response = await router.complete(prompt="Analyze tokens")

        assert response.latency_seconds > 0.0
        # Groq openai/gpt-oss-120b: Input $0.35 / 1M, Output $0.75 / 1M
        # Cost = (1000 * 0.35 + 500 * 0.75) / 1,000,000 = 0.000725
        expected_cost = round((1000 * 0.35 + 500 * 0.75) / 1_000_000, 8)
        assert response.cost_usd == expected_cost

        assert len(router.call_history) == 1
        record = router.call_history[0]
        assert record.provider == "groq"
        assert record.model == "openai/gpt-oss-120b"
        assert record.prompt_tokens == 1000
        assert record.completion_tokens == 500
        assert record.total_tokens == 1500
        assert record.cost_usd == expected_cost
        assert record.latency_seconds == response.latency_seconds

    asyncio.run(run())


def test_model_router_cost_accurate_on_fallback():
    """Verify that when fallback is activated, the cost is calculated strictly using the fallback model's pricing."""
    async def run():
        async def mock_fallback_caller(provider: str, model: str, prompt: str, **kwargs):
            return LLMResponse(
                content="OpenRouter Fallback Response",
                model=model,
                provider=provider,
                usage={"prompt_tokens": 2000, "completion_tokens": 1000, "total_tokens": 3000},
            )

        # Primary is Groq 70B (Input $0.59 / 1M, Output $0.79 / 1M)
        primary = ProviderConfig(provider="groq", model="llama-3.3-70b")
        # Fallback is OpenRouter 70B (Input $0.10 / 1M, Output $0.32 / 1M)
        fallback = ProviderConfig(provider="openrouter", model="meta-llama/llama-3.3-70b-instruct")
        router = ModelRouter(providers=[primary], fallback=fallback, client_caller=mock_fallback_caller)

        # Put primary in cooldown so fallback triggers
        router.mark_cooldown(provider="groq", model="llama-3.3-70b", duration_seconds=60)

        response = await router.complete(prompt="Need fallback")

        assert response.provider == "openrouter"
        assert response.model == "meta-llama/llama-3.3-70b-instruct"

        # OpenRouter pricing MUST be used:
        # Cost = (2000 * 0.10 + 1000 * 0.32) / 1,000,000 = 0.00052
        expected_fallback_cost = round((2000 * 0.10 + 1000 * 0.32) / 1_000_000, 8)
        assert response.cost_usd == expected_fallback_cost

        # Verify call history records fallback provider and model
        record = router.call_history[0]
        assert record.provider == "openrouter"
        assert record.model == "meta-llama/llama-3.3-70b-instruct"
        assert record.cost_usd == expected_fallback_cost

    asyncio.run(run())


def test_model_router_ollama_cloud_cost_calculation():
    """Verify that Ollama Cloud models use published Ollama Cloud rates."""
    async def run():
        async def mock_caller(provider: str, model: str, prompt: str, **kwargs):
            return LLMResponse(
                content="Ollama 120B Response",
                model=model,
                provider=provider,
                usage={"prompt_tokens": 10000, "completion_tokens": 2000, "total_tokens": 12000},
            )

        ollama_cfg = ProviderConfig(
            provider="ollama",
            model="gpt-oss:120b",
            api_key="key",
            api_base="https://ollama.com/v1",
        )
        fallback = ProviderConfig(provider="openrouter", model="meta-llama/llama-3.3-70b")
        router = ModelRouter(providers=[ollama_cfg], fallback=fallback, client_caller=mock_caller)

        response = await router.complete(prompt="Deep reasoning")

        # Ollama Cloud gpt-oss:120b: Input $0.15 / 1M, Output $0.60 / 1M
        # Cost = (10000 * 0.15 + 2000 * 0.60) / 1,000,000 = 0.0027
        expected_cost = round((10000 * 0.15 + 2000 * 0.60) / 1_000_000, 8)
        assert response.cost_usd == expected_cost

    asyncio.run(run())


def test_model_router_telemetry_summary_aggregation():
    """Verify get_telemetry_summary aggregates across multiple calls and resets cleanly."""
    async def run():
        models_to_return = [
            ("groq", "openai/gpt-oss-120b", {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}),
            ("groq", "openai/gpt-oss-120b", {"prompt_tokens": 2000, "completion_tokens": 1000, "total_tokens": 3000}),
            ("ollama", "gpt-oss:120b", {"prompt_tokens": 5000, "completion_tokens": 2000, "total_tokens": 7000}),
        ]
        call_idx = 0

        async def mock_multi_caller(provider: str, model: str, prompt: str, **kwargs):
            nonlocal call_idx
            p, m, u = models_to_return[call_idx]
            call_idx += 1
            return LLMResponse(content="ok", model=m, provider=p, usage=u)

        cfg1 = ProviderConfig(provider="groq", model="openai/gpt-oss-120b")
        cfg2 = ProviderConfig(provider="ollama", model="gpt-oss:120b")
        fallback = ProviderConfig(provider="openrouter", model="meta-llama/llama-3.3-70b")

        router = ModelRouter(providers=[cfg1], fallback=fallback, client_caller=mock_multi_caller)

        # Call 1: Groq
        await router.complete(prompt="Prompt 1")
        # Call 2: Groq
        await router.complete(prompt="Prompt 2")

        # Route to Ollama for Call 3
        router.providers = [cfg2]
        await router.complete(prompt="Prompt 3")

        summary = router.get_telemetry_summary()
        assert summary["total_calls"] == 3
        assert summary["total_prompt_tokens"] == 1000 + 2000 + 5000
        assert summary["total_completion_tokens"] == 500 + 1000 + 2000
        assert summary["total_tokens"] == 1500 + 3000 + 7000
        assert summary["total_latency_seconds"] >= 0.0
        assert summary["total_cost_usd"] > 0.0

        # Check by_model breakdown
        assert "groq/openai/gpt-oss-120b" in summary["by_model"]
        assert "ollama/gpt-oss:120b" in summary["by_model"]
        assert summary["by_model"]["groq/openai/gpt-oss-120b"]["calls"] == 2
        assert summary["by_model"]["ollama/gpt-oss:120b"]["calls"] == 1

        # Test reset_telemetry
        router.reset_telemetry()
        reset_summary = router.get_telemetry_summary()
        assert reset_summary["total_calls"] == 0
        assert reset_summary["total_tokens"] == 0
        assert reset_summary["total_cost_usd"] == 0.0
        assert len(reset_summary["by_model"]) == 0

    asyncio.run(run())


def test_native_httpx_chat_completion_success():
    """Verify native httpx execution parses OpenAI-compatible response correctly."""
    from unittest.mock import AsyncMock, patch
    import httpx

    async def run():
        mock_response_payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Deep research response",
                        "reasoning": "Thinking step by step",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "tavily_search", "arguments": '{"query": "AI"}'},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
        }

        mock_http_resp = httpx.Response(
            status_code=200,
            json=mock_response_payload,
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
        )

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_http_resp

            primary = ProviderConfig(provider="groq", model="llama-3.3-70b", api_key="gsk_mock")
            fallback = ProviderConfig(provider="openrouter", model="meta-llama/llama-3.3-70b")
            # client_caller is None -> triggers native httpx path!
            router = ModelRouter(providers=[primary], fallback=fallback)

            resp = await router.complete(prompt="Research AI agents")

            assert resp.content == "Deep research response"
            assert resp.reasoning == "Thinking step by step"
            assert resp.finish_reason == "tool_calls"
            assert resp.tool_calls is not None
            assert len(resp.tool_calls) == 1
            assert resp.tool_calls[0]["function"]["name"] == "tavily_search"
            assert resp.usage["total_tokens"] == 200

            # Verify POST was made with correct endpoint, payload and headers
            mock_post.assert_called_once()
            call_args, call_kwargs = mock_post.call_args
            assert call_args[0] == "https://api.groq.com/openai/v1/chat/completions"
            assert call_kwargs["headers"]["Authorization"] == "Bearer gsk_mock"
            assert call_kwargs["json"]["model"] == "llama-3.3-70b"
            assert call_kwargs["json"]["messages"] == [{"role": "user", "content": "Research AI agents"}]

    asyncio.run(run())


def test_native_httpx_429_dynamic_cooldown_and_fallback():
    """Verify HTTP 429 parses retry-after header, marks cooldown, and activates fallback."""
    from unittest.mock import AsyncMock, patch
    import httpx

    async def run():
        mock_429_resp = httpx.Response(
            status_code=429,
            headers={"retry-after": "8"},
            text='{"error": {"message": "Rate limit exceeded"}}',
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
        )
        mock_200_resp = httpx.Response(
            status_code=200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "OpenRouter Fallback Done"}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            },
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
        )

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            # Primary Groq fails with 429, fallback OpenRouter succeeds
            mock_post.side_effect = [mock_429_resp, mock_200_resp]

            primary = ProviderConfig(
                provider="groq", model="llama-3.3-70b", api_key="gsk_mock", max_retries=1
            )
            fallback = ProviderConfig(
                provider="openrouter",
                model="nvidia/nemotron-3-super-120b-a12b:free",
                api_key="sk_openrouter",
            )
            router = ModelRouter(providers=[primary], fallback=fallback)

            resp = await router.complete(prompt="Need emergency query")

            assert resp.content == "OpenRouter Fallback Done"
            assert resp.provider == "openrouter"
            # Primary model must be marked in cooldown
            assert router.is_in_cooldown(provider="groq", model="llama-3.3-70b")

            # Verify OpenRouter headers were sent
            second_call_kwargs = mock_post.call_args_list[1][1]
            headers = second_call_kwargs["headers"]
            assert headers["HTTP-Referer"] == "https://github.com/langchain-ai/open_deep_research"
            assert headers["X-Title"] == "Deep Research Agent"

    asyncio.run(run())


def test_native_httpx_preserves_groq_compound_model_id():
    """Groq Compound IDs are namespaced and must not be reduced to `compound`."""
    from unittest.mock import AsyncMock, patch
    import httpx

    async def run():
        mock_response = httpx.Response(
            status_code=200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Compound response"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
        )

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            router = ModelRouter(
                providers=[
                    ProviderConfig(
                        provider="groq",
                        model="groq/compound",
                        api_key="gsk_mock",
                        max_retries=1,
                    )
                ]
            )

            response = await router.complete(prompt="Research AI education")

            assert response.content == "Compound response"
            payload = mock_post.call_args.kwargs["json"]
            assert payload["model"] == "groq/compound"
            assert "reasoning_format" not in payload

    asyncio.run(run())


def test_groq_tool_use_failed_defensive_recovery():
    """Verify Groq HTTP 400 with tool_use_failed recovers generation without raising error."""
    from unittest.mock import AsyncMock, patch
    import httpx

    async def run():
        mock_groq_400_resp = httpx.Response(
            status_code=400,
            json={
                "error": {
                    "message": "Tool choice is none, but model called a tool",
                    "type": "invalid_request_error",
                    "code": "tool_use_failed",
                    "failed_generation": '{"name": "delegate_research_queries", "arguments": {"queries": []}}',
                }
            },
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
        )

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_groq_400_resp

            primary = ProviderConfig(provider="groq", model="openai/gpt-oss-120b", api_key="gsk_mock")
            fallback = ProviderConfig(provider="openrouter", model="meta-llama/llama-3.3-70b")
            router = ModelRouter(providers=[primary], fallback=fallback)

            resp = await router.complete(prompt="Evaluate research gap")

            assert resp.content == '{"name": "delegate_research_queries", "arguments": {"queries": []}}'
            assert resp.provider == "groq"
            assert resp.model == "openai/gpt-oss-120b"
            assert resp.usage["total_tokens"] > 0

    asyncio.run(run())


