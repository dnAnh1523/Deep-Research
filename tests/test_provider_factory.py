"""Tests for provider-agnostic runtime configuration."""

import json
import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from infra.llm.factory import load_provider_config
from infra.model_router import ModelRouter, ProviderConfig
from infra.settings import AppSettings


def test_load_provider_config_supports_arbitrary_openai_compatible_gateway(tmp_path):
    config_path = tmp_path / "providers.json"
    config_path.write_text(
        json.dumps(
            {
                "primary": [
                    {
                        "name": "private-gateway",
                        "protocol": "openai-compatible",
                        "model": "research-model-v7",
                        "base_url": "http://gateway.test/v1",
                        "api_key_env": "PRIVATE_GATEWAY_KEY",
                        "supports_tools": True,
                    }
                ],
                "fallback": None,
            }
        ),
        encoding="utf-8",
    )

    settings = AppSettings(provider_config_file=str(config_path))
    primary, fallback = load_provider_config(
        settings,
        environ={"PRIVATE_GATEWAY_KEY": "test-secret"},
    )

    assert fallback is None
    assert len(primary) == 1
    assert primary[0].provider == "private-gateway"
    assert primary[0].model == "research-model-v7"
    assert primary[0].api_base == "http://gateway.test/v1"
    assert primary[0].api_key == "test-secret"


def test_load_provider_config_supports_native_anthropic_protocol(tmp_path):
    config_path = tmp_path / "providers.json"
    config_path.write_text(
        json.dumps(
            {
                "primary": [
                    {
                        "provider": "anthropic",
                        "protocol": "anthropic",
                        "model": "claude-test",
                        "base_url": "https://anthropic.test/v1",
                        "api_key_env": "ANTHROPIC_API_KEY",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    primary, _ = load_provider_config(
        AppSettings(provider_config_file=str(config_path)),
        environ={"ANTHROPIC_API_KEY": "test-secret"},
    )

    assert primary[0].protocol == "anthropic"
    assert primary[0].api_key == "test-secret"


def test_model_router_translates_anthropic_messages_and_tools():
    async def run():
        response = httpx.Response(
            status_code=200,
            json={
                "content": [
                    {"type": "text", "text": "Anthropic response"},
                    {
                        "type": "tool_use",
                        "id": "tool_1",
                        "name": "search",
                        "input": {"query": "AI"},
                    },
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 12, "output_tokens": 8},
            },
            request=httpx.Request("POST", "https://api.anthropic.test/v1/messages"),
        )
        primary = ProviderConfig(
            provider="anthropic",
            protocol="anthropic",
            model="claude-test",
            api_key="sk-test",
            api_base="https://api.anthropic.test/v1",
            max_retries=1,
        )
        router = ModelRouter(providers=[primary], fallback=None)
        tool = {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search the web",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
        }

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as post:
            post.return_value = response
            result = await router.complete(prompt="Find evidence", tools=[tool], max_tokens=128)

        assert result.content == "Anthropic response"
        assert result.tool_calls[0]["function"]["name"] == "search"
        assert result.usage == {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
        call_args, call_kwargs = post.call_args
        assert call_args[0] == "https://api.anthropic.test/v1/messages"
        assert call_kwargs["headers"]["x-api-key"] == "sk-test"
        assert call_kwargs["json"]["max_tokens"] == 128
        assert call_kwargs["json"]["tools"][0]["input_schema"]["type"] == "object"

    asyncio.run(run())
