"""Tests for infra.search_client."""

import asyncio
import httpx
from infra.interfaces import SearchClient, SearchResult
from infra.search_client import DEFAULT_SEARCH_TIMEOUT, TavilySearchClient


def test_tavily_search_client_conforms_to_search_client_protocol():
    client = TavilySearchClient(api_key="test-key")
    assert isinstance(client, SearchClient)
    assert client.timeout_seconds == DEFAULT_SEARCH_TIMEOUT


def test_search_results_mapping_does_not_leak_tavily_schema():
    async def run():
        raw_tavily_response = {
            "results": [
                {
                    "title": "Quantum Error Correction",
                    "url": "https://nature.com/articles/s41586",
                    "content": "Surface codes provide fault tolerance...",
                    "raw_content": "Full raw page content...",
                    "published_date": "2026-04-15",
                    "score": 0.98,  # Tavily-specific field that should NOT leak
                }
            ]
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=raw_tavily_response)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as mock_http:
            search_client = TavilySearchClient(
                api_key="test-key",
                http_client=mock_http,
            )
            results = await search_client.search(
                query="Quantum error correction", max_results=1
            )

        assert len(results) == 1
        item = results[0]
        assert isinstance(item, SearchResult)
        assert item.title == "Quantum Error Correction"
        assert item.url == "https://nature.com/articles/s41586"
        assert item.content == "Surface codes provide fault tolerance..."
        assert item.raw_content == "Full raw page content..."
        assert item.published_date == "2026-04-15"
        # Ensure no dict leakage
        assert not hasattr(item, "score")

    asyncio.run(run())


def test_search_retry_exponential_backoff_on_failure():
    async def run():
        attempts = 0
        sleeps = []

        async def mock_sleep(seconds: float):
            sleeps.append(seconds)

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return httpx.Response(429, json={"error": "Rate limit exceeded"})
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Success",
                            "url": "https://ok.com",
                            "content": "Done",
                        }
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        original_sleep = asyncio.sleep
        asyncio.sleep = mock_sleep

        try:
            async with httpx.AsyncClient(transport=transport) as mock_http:
                search_client = TavilySearchClient(
                    api_key="test-key",
                    max_retries=3,
                    base_delay_seconds=0.25,
                    http_client=mock_http,
                )
                results = await search_client.search(query="Retry test")

            assert len(results) == 1
            assert attempts == 3
            assert sleeps == [0.25, 0.5]
        finally:
            asyncio.sleep = original_sleep

    asyncio.run(run())
