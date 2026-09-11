"""Tests for infra.interfaces."""

import inspect
from dataclasses import is_dataclass
from infra.interfaces import (
    LLMProvider,
    LLMResponse,
    SearchClient,
    SearchResult,
)


def test_llm_response_dataclass_properties():
    assert is_dataclass(LLMResponse)
    resp = LLMResponse(content="Test content")
    assert resp.content == "Test content"
    assert resp.tool_calls is None
    assert resp.model is None
    assert resp.provider is None
    assert resp.usage is None

    full_resp = LLMResponse(
        content="Report content",
        tool_calls=[{"name": "search", "arguments": {"query": "AI"}}],
        model="openai/gpt-oss-120b",
        provider="groq",
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )
    assert full_resp.content == "Report content"
    assert len(full_resp.tool_calls) == 1
    assert full_resp.provider == "groq"
    assert full_resp.usage["total_tokens"] == 150


def test_search_result_dataclass_properties():
    assert is_dataclass(SearchResult)
    res = SearchResult(
        url="https://example.com/article",
        title="Sample Title",
        content="Summary content",
    )
    assert res.url == "https://example.com/article"
    assert res.title == "Sample Title"
    assert res.content == "Summary content"
    assert res.raw_content is None

    full_res = SearchResult(
        url="https://example.com/full",
        title="Full Title",
        content="Summary",
        raw_content="<html><body>Full page body</body></html>",
    )
    assert full_res.raw_content is not None


def test_llm_provider_protocol_conformance():
    class DummyLLMProvider:
        async def complete(
            self, *, prompt: str, tools: list[dict] | None = None
        ) -> LLMResponse:
            return LLMResponse(content="Dummy response")

    dummy = DummyLLMProvider()
    assert isinstance(dummy, LLMProvider)
    assert inspect.iscoroutinefunction(dummy.complete)


def test_search_client_protocol_conformance():
    class DummySearchClient:
        async def search(
            self, *, query: str, max_results: int = 5
        ) -> list[SearchResult]:
            return [
                SearchResult(
                    url="https://test.com",
                    title="Test",
                    content="Content",
                )
            ]

    dummy = DummySearchClient()
    assert isinstance(dummy, SearchClient)
    assert inspect.iscoroutinefunction(dummy.search)


def test_non_conforming_classes_fail_protocol_check():
    class IncompleteLLM:
        # missing async complete
        def generate(self, prompt: str) -> str:
            return prompt

    assert not isinstance(IncompleteLLM(), LLMProvider)

    class IncompleteSearch:
        # synchronous search instead of async
        def search(self, query: str) -> list[dict]:
            return []

    # Note: protocol requires complete/search method
    class EmptyClient:
        pass

    assert not isinstance(EmptyClient(), SearchClient)
