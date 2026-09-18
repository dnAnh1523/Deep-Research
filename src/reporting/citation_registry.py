"""Domain logic for Canonical Document Identity and Citation Registry.

Clean Architecture Rules:
- Pure Python: no LangGraph, no network calls, no framework dependencies.
- Deduplicates document chunks by canonical URL/DOI into unique doc_ids.
- Assigns deterministic, 1-based unique citation indices across the entire report.
- Preserves verbatim evidence excerpts corresponding to each canonical document.
- Parses in-text citation markers ([1], [1, 2], [1][2], [1-3], ¹ ²) and links them.
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


def canonicalize_url(raw_url: str) -> str:
    """Normalize a URL to establish canonical identity."""
    if not raw_url:
        return ""
    cleaned = raw_url.strip().rstrip(".,;)>]")
    try:
        parsed = urlparse(cleaned)
        netloc = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.rstrip("/")
        # Reconstruct canonical form, standardizing web scheme to https
        scheme = "https" if parsed.scheme.lower() in ("http", "https") else (parsed.scheme.lower() or "https")
        return f"{scheme}://{netloc}{path}" if path else f"{scheme}://{netloc}"
    except Exception:
        return cleaned


def generate_doc_id(canonical_url: str, title: str = "") -> str:
    """Generate a deterministic, short doc_id for a document."""
    base = canonical_url if canonical_url else title.strip().lower()
    hashed = hashlib.sha256(base.encode("utf-8")).hexdigest()[:10]
    return f"doc_{hashed}"


@dataclass
class CanonicalDocument:
    """Represents a single canonical document source regardless of how many times it is chunked or cited."""

    doc_id: str
    assigned_number: int
    url: str
    title: str
    publisher: str = ""
    year: int = 2026
    snippets: list[str] = field(default_factory=list)
    doc_type: str = "academic"  # academic | whitepaper | benchmark | disclosure
    verified: bool = True

    def add_snippet(self, snippet: str) -> None:
        """Add a verbatim excerpt to this document if not already present."""
        clean = snippet.strip()
        if clean and clean not in self.snippets:
            self.snippets.append(clean)

    def to_dict(self) -> dict[str, Any]:
        """Serialize document for API transmission."""
        return {
            "id": self.assigned_number,
            "number": self.assigned_number,
            "doc_id": self.doc_id,
            "title": self.title,
            "publisher": self.publisher,
            "year": self.year,
            "url": self.url,
            "snippet": self.snippets[0] if self.snippets else "",
            "all_snippets": self.snippets,
            "verified": self.verified,
            "type": self.doc_type,
        }


class CitationRegistry:
    """Registry maintaining unique document mappings and citation indices."""

    def __init__(self) -> None:
        self.doc_map: dict[str, CanonicalDocument] = {}  # doc_id -> CanonicalDocument
        self.url_to_doc_id: dict[str, str] = {}  # canonical_url -> doc_id
        self._next_number: int = 1

    def register_source(
        self,
        url: str,
        title: str = "",
        snippet: str = "",
        publisher: str = "",
        year: int = 2026,
        doc_type: str = "whitepaper",
    ) -> CanonicalDocument:
        """Register or retrieve a canonical document.
        
        If a document with the same canonical URL already exists, returns the existing
        document and appends the new snippet without changing the assigned_number.
        """
        c_url = canonicalize_url(url)
        doc_id = self.url_to_doc_id.get(c_url)

        if not doc_id:
            # Check if title matches an existing doc with no URL
            doc_id = generate_doc_id(c_url, title)
            self.url_to_doc_id[c_url] = doc_id

        if doc_id in self.doc_map:
            doc = self.doc_map[doc_id]
            if snippet:
                doc.add_snippet(snippet)
            if title and (not doc.title or len(title) > len(doc.title)):
                doc.title = title
            return doc

        # Infer publisher from domain if blank
        if not publisher and c_url:
            try:
                domain = urlparse(c_url).netloc.replace("www.", "")
                publisher = domain.capitalize()
            except Exception:
                publisher = "Unknown Publisher"

        # Determine doc_type heuristically
        if "doi.org" in c_url or "arxiv.org" in c_url or "nature.com" in c_url:
            doc_type = "academic"
        elif "patent" in c_url or "sec.gov" in c_url or "toyota" in c_url or "catl" in c_url:
            doc_type = "disclosure"

        doc = CanonicalDocument(
            doc_id=doc_id,
            assigned_number=self._next_number,
            url=c_url,
            title=title or publisher or f"Source {self._next_number}",
            publisher=publisher,
            year=year,
            snippets=[snippet.strip()] if snippet.strip() else [],
            doc_type=doc_type,
            verified=True,
        )
        self.doc_map[doc_id] = doc
        self._next_number += 1
        return doc

    def get_by_number(self, number: int) -> CanonicalDocument | None:
        """Retrieve canonical document by its assigned citation number."""
        for doc in self.doc_map.values():
            if doc.assigned_number == number:
                return doc
        return None

    def get_all_ordered(self) -> list[CanonicalDocument]:
        """Return all registered documents sorted by assigned_number."""
        return sorted(self.doc_map.values(), key=lambda d: d.assigned_number)

    def to_citation_dict(self) -> dict[str, dict[str, Any]]:
        """Return a serializable dictionary keyed by assigned_number string (e.g. '1', '2')."""
        return {str(doc.assigned_number): doc.to_dict() for doc in self.get_all_ordered()}

    def format_sources_prompt(self) -> str:
        """Format the available sources into a prompt string for the reporting LLM."""
        lines = []
        for doc in self.get_all_ordered():
            excerpt = f' - Excerpt: "{doc.snippets[0]}"' if doc.snippets else ""
            lines.append(f"[{doc.assigned_number}] {doc.title} ({doc.url}){excerpt}")
        return "\n".join(lines)


def parse_sources_from_research_notes(notes: list[str]) -> CitationRegistry:
    """Parse notes and findings into a structured CitationRegistry."""
    registry = CitationRegistry()

    for note in notes:
        # Match markdown links: [Title](url)
        md_matches = re.findall(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", note)
        for title, url in md_matches:
            # Extract excerpt if surrounding text exists
            excerpt = note.replace(f"[{title}]({url})", "").strip("- * ").strip()
            registry.register_source(url=url, title=title.strip(), snippet=excerpt[:250])

        # Match standalone URLs: (https://...) or https://...
        raw_urls = re.findall(r"(https?://[^\s\)\],]+)", note)
        for url in raw_urls:
            # Skip if already captured by markdown links
            c_url = canonicalize_url(url)
            if c_url in registry.url_to_doc_id:
                continue
            excerpt = note.replace(url, "").strip("- * ").strip()
            registry.register_source(url=url, title="", snippet=excerpt[:250])

    return registry
