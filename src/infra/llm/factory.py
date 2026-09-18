"""Build the model router from a user-owned provider configuration.

The factory is intentionally small: provider-specific HTTP behavior lives in
`infra.model_router`, while this module only translates JSON/environment values
into infrastructure DTOs.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from infra.model_router import ModelRouter, ProviderConfig
from infra.settings import AppSettings

logger = logging.getLogger(__name__)

DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://127.0.0.1:11434/v1",
}

DEFAULT_PROTOCOLS = {"anthropic": "anthropic"}
RoleProviderConfig = tuple[list[ProviderConfig], ProviderConfig | None]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Provider config must be a JSON object: {path}")
    return payload


def _provider_from_dict(
    raw: dict[str, Any], *, source: str, environ: dict[str, str] | None = None
) -> ProviderConfig:
    provider = str(raw.get("provider") or raw.get("name") or "").strip()
    model = str(raw.get("model") or "").strip()
    if not provider or not model:
        raise ValueError(f"Provider entries require provider/name and model ({source})")

    api_key = raw.get("api_key")
    api_key_env = raw.get("api_key_env")
    if api_key is None and api_key_env:
        values = environ or os.environ
        api_key = values.get(str(api_key_env)) or None

    protocol = str(raw.get("protocol") or DEFAULT_PROTOCOLS.get(provider, "openai-compatible"))
    base_url = raw.get("base_url") or raw.get("api_base") or DEFAULT_BASE_URLS.get(provider)
    if not base_url:
        raise ValueError(
            f"Provider '{provider}' needs base_url/api_base because it has no known default ({source})"
        )

    extra_params = raw.get("extra_params") or {}
    if not isinstance(extra_params, dict):
        raise ValueError(f"extra_params must be an object ({source})")

    return ProviderConfig(
        provider=provider,
        model=model,
        api_key=str(api_key) if api_key else None,
        api_base=str(base_url),
        protocol=protocol,
        supports_tools=bool(raw.get("supports_tools", True)),
        supports_structured_output=bool(raw.get("supports_structured_output", False)),
        max_retries=int(raw.get("max_retries", 3)),
        base_delay_seconds=float(raw.get("base_delay_seconds", 1.0)),
        timeout_seconds=float(raw.get("timeout_seconds", 60.0)),
        extra_params=extra_params,
    )


def load_provider_config(
    settings: AppSettings,
    *,
    environ: dict[str, str] | None = None,
) -> tuple[list[ProviderConfig], ProviderConfig | None]:
    """Load configured primary providers and an optional fallback.

    If the configured JSON file does not exist, a compatibility discovery path
    reads common provider environment variables. Arbitrary providers should use
    JSON because they need a custom base URL and model name.
    """
    env = environ or os.environ
    config_path = settings.resolve_path(settings.provider_config_file)
    if config_path.exists():
        raw = _read_json(config_path)
        roles_raw = raw.get("roles")
        if isinstance(roles_raw, dict) and isinstance(roles_raw.get("brain"), dict):
            return _load_provider_block(
                roles_raw["brain"], source=str(config_path), environ=env
            )
        return _load_provider_block(raw, source=str(config_path), environ=env)

    discovered: list[ProviderConfig] = []
    known = ["openai", "anthropic", "groq", "cerebras", "openrouter", "ollama"]
    for provider in known:
        key_env = f"{provider.upper()}_API_KEY"
        api_key = env.get(key_env)
        local_ollama = provider == "ollama" and (
            settings.local_slm_enabled or env.get("LOCAL_SLM_MODEL")
        )
        if not api_key and not local_ollama:
            continue

        model = env.get(f"{provider.upper()}_MODEL")
        if provider == "ollama":
            model = model or settings.local_slm_model or "qwen2.5:7b"
            base_url = env.get("OLLAMA_BASE_URL") or settings.local_slm_base_url
            api_key = api_key or "ollama"
        elif provider == "anthropic":
            model = model or "claude-3-5-sonnet-latest"
            base_url = env.get("ANTHROPIC_BASE_URL") or DEFAULT_BASE_URLS[provider]
        else:
            model = model or env.get("DEFAULT_MODEL")
            if not model:
                logger.warning("Skipping %s: set %s_MODEL or DEFAULT_MODEL", provider, provider.upper())
                continue
            base_url = env.get(f"{provider.upper()}_BASE_URL") or DEFAULT_BASE_URLS[provider]

        discovered.append(
            _provider_from_dict(
                {
                    "provider": provider,
                    "model": model,
                    "api_key": api_key,
                    "base_url": base_url,
                    "protocol": DEFAULT_PROTOCOLS.get(provider, "openai-compatible"),
                },
                source="environment",
            )
        )

    fallback_provider = env.get("LLM_FALLBACK_PROVIDER")
    fallback_model = env.get("LLM_FALLBACK_MODEL")
    fallback: ProviderConfig | None = None
    if fallback_provider and fallback_model:
        fallback = _provider_from_dict(
            {
                "provider": fallback_provider,
                "model": fallback_model,
                "api_key": env.get(
                    env.get("LLM_FALLBACK_API_KEY_ENV", "")
                ),
                "base_url": env.get("LLM_FALLBACK_BASE_URL")
                or DEFAULT_BASE_URLS.get(fallback_provider),
                "protocol": DEFAULT_PROTOCOLS.get(fallback_provider, "openai-compatible"),
            },
            source="environment fallback",
        )
    return discovered, fallback


def _load_provider_block(
    raw: dict[str, Any], *, source: str, environ: dict[str, str]
) -> RoleProviderConfig:
    """Parse one provider block shared by legacy and role-based config."""
    if "primary" not in raw and raw.get("provider"):
        raw = {"primary": [raw]}

    primary_raw = raw.get("primary", [])
    if not isinstance(primary_raw, list):
        raise ValueError("providers.primary must be an array")
    primary = [
        _provider_from_dict(item, source=source, environ=environ)
        for item in primary_raw
        if isinstance(item, dict)
    ]

    fallback_raw = raw.get("fallback")
    fallback = (
        _provider_from_dict(fallback_raw, source=source, environ=environ)
        if isinstance(fallback_raw, dict)
        else None
    )
    return primary, fallback


def load_role_provider_configs(
    settings: AppSettings,
    *,
    environ: dict[str, str] | None = None,
) -> dict[str, RoleProviderConfig]:
    """Load optional role-specific provider blocks from ``providers.json``.

    Role blocks intentionally stay at the composition seam: graph nodes only
    receive the ``brain`` or ``worker`` adapter and do not know model names.
    """
    env = environ or os.environ
    config_path = settings.resolve_path(settings.provider_config_file)
    if not config_path.exists():
        return {}

    raw = _read_json(config_path)
    roles_raw = raw.get("roles")
    if not isinstance(roles_raw, dict):
        return {}

    roles: dict[str, RoleProviderConfig] = {}
    for role_name, role_raw in roles_raw.items():
        if isinstance(role_name, str) and isinstance(role_raw, dict):
            roles[role_name] = _load_provider_block(
                role_raw, source=str(config_path), environ=env
            )
    return roles


def _router_from_provider_config(config: RoleProviderConfig) -> ModelRouter | None:
    providers, fallback = config
    if not providers:
        return None
    return ModelRouter(providers=providers, fallback=fallback)


def build_model_routers(
    settings: AppSettings,
    *,
    environ: dict[str, str] | None = None,
) -> tuple[ModelRouter | None, ModelRouter | None]:
    """Build the ``brain`` and ``worker`` routers with legacy fallback.

    A legacy single-provider config deliberately returns the same adapter for
    both roles, preserving the original one-model runtime behaviour.
    """
    roles = load_role_provider_configs(settings, environ=environ)
    if not roles:
        shared = build_model_router(settings, environ=environ)
        return shared, shared

    brain = _router_from_provider_config(roles.get("brain", ([], None)))
    worker = _router_from_provider_config(roles.get("worker", ([], None)))
    brain = brain or worker
    worker = worker or brain
    return brain, worker


def build_model_router(
    settings: AppSettings,
    *,
    environ: dict[str, str] | None = None,
) -> ModelRouter | None:
    """Create a router or return `None` when no usable provider is configured."""
    providers, fallback = load_provider_config(settings, environ=environ)
    if not providers:
        return None
    return ModelRouter(providers=providers, fallback=fallback)
