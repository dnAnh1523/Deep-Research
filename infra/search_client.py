"""Humble Object wrapping web search providers (Tavily).

Conforms strictly to SearchClient protocol, preventing any vendor SDK types
from leaking into caller domain nodes.
"""

import asyncio
import os
import httpx
from infra.interfaces import SearchClient, SearchResult

DEFAULT_SEARCH_TIMEOUT: float = 10.0


class TavilySearchClient:
    """Search client adapter communicating with Tavily API.

    Implements infra.interfaces.SearchClient protocol.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_seconds: float = DEFAULT_SEARCH_TIMEOUT,
        max_retries: int = 3,
        base_delay_seconds: float = 1.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("TAVILY_API_KEY", "")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self._http_client = http_client

    async def search(
        self, *, query: str, max_results: int = 5
    ) -> list[SearchResult]:
        """Perform search query and return normalized list of SearchResult dataclasses."""
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
        }

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                if self._http_client is not None:
                    response = await self._http_client.post(
                        url, json=payload, timeout=self.timeout_seconds
                    )
                else:
                    async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                        response = await client.post(url, json=payload)

                response.raise_for_status()
                data = response.json()
                results_raw = data.get("results", [])

                return [
                    SearchResult(
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        content=item.get("content", ""),
                        raw_content=item.get("raw_content"),
                        published_date=item.get("published_date"),
                    )
                    for item in results_raw
                ]

            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.base_delay_seconds * (2**attempt))
                else:
                    break

        raise last_exc or RuntimeError(f"Tavily search failed for query: '{query}'")
