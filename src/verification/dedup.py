"""Deduplication logic for research sources."""

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class Source:
    """Represents a research information source."""

    url: str
    title: str


def _normalize_domain(url: str) -> str:
    """Extract and normalize domain by converting to lowercase and stripping 'www.' prefix."""
    parsed = urlparse(url)
    netloc = parsed.netloc or parsed.path.split("/")[0]
    host = netloc.split(":")[0].strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _normalize_title(title: str) -> str:
    """Normalize title by lowercasing and collapsing contiguous whitespace."""
    return " ".join(title.strip().lower().split())


def _normalize_url_path(url: str) -> str:
    """Normalize URL path by stripping trailing slash and lowercasing."""
    parsed = urlparse(url)
    return parsed.path.rstrip("/").lower()


class _DisjointSet:
    """Simple Disjoint Set Union (DSU) helper for grouping duplicate sources."""

    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        if self.parent[item] == item:
            return item
        self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, first: int, second: int) -> None:
        root_first = self.find(first)
        root_second = self.find(second)
        if root_first != root_second:
            self.parent[root_first] = root_second


def group_likely_duplicates(sources: list[Source]) -> list[list[Source]]:
    """Group sources that are likely duplicates.

    Rules:
    - 2 sources from different domains are ALWAYS independent (never grouped together).
    - Domain comparison ignores 'www.' prefix and is case-insensitive.
    - Title comparison is case-insensitive and collapses extra whitespace.
    - Within the same domain, sources sharing the same normalized title or normalized URL path are grouped.

    Returns:
        list[list[Source]]: List of grouped sources, preserving order of first appearance.
    """
    if not sources:
        return []

    count = len(sources)
    dsu = _DisjointSet(count)

    seen_title_key: dict[tuple[str, str], int] = {}
    seen_url_key: dict[tuple[str, str], int] = {}

    for idx, source in enumerate(sources):
        domain = _normalize_domain(source.url)
        norm_title = _normalize_title(source.title)
        norm_path = _normalize_url_path(source.url)

        if norm_title:
            title_key = (domain, norm_title)
            if title_key in seen_title_key:
                dsu.union(idx, seen_title_key[title_key])
            else:
                seen_title_key[title_key] = idx

        if norm_path:
            url_key = (domain, norm_path)
            if url_key in seen_url_key:
                dsu.union(idx, seen_url_key[url_key])
            else:
                seen_url_key[url_key] = idx

    groups_dict: dict[int, list[Source]] = {}
    for idx, source in enumerate(sources):
        root = dsu.find(idx)
        if root not in groups_dict:
            groups_dict[root] = []
        groups_dict[root].append(source)

    return list(groups_dict.values())


def count_independent_sources(sources: list[Source]) -> int:
    """Return the number of independent source groups (not raw count)."""
    return len(group_likely_duplicates(sources))
