"""Tests for Canonical Document Identity and Citation Registry."""

import pytest
from reporting.citation_registry import (
    CitationRegistry,
    canonicalize_url,
    generate_doc_id,
    parse_sources_from_research_notes,
)


def test_canonicalize_url_normalizes_properly():
    url1 = "https://www.nature.com/articles/s41560-025-01822-x/"
    url2 = "http://nature.com/articles/s41560-025-01822-x"
    assert canonicalize_url(url1) == canonicalize_url(url2)
    assert canonicalize_url(url1) == "https://nature.com/articles/s41560-025-01822-x"


def test_single_document_multiple_chunks_maintains_single_citation_number():
    registry = CitationRegistry()

    # Chunk 1 of Toyota disclosure
    doc1 = registry.register_source(
        url="https://global.toyota/en/battery-roadmap",
        title="Toyota Roadmap 2026",
        snippet="Toyota bắt đầu sản xuất thử nghiệm năm 2026 tại Aichi.",
    )

    # Chunk 2 of same Toyota disclosure (different fragment/excerpt)
    doc2 = registry.register_source(
        url="https://www.global.toyota/en/battery-roadmap/",
        title="Toyota Roadmap 2026 Extended",
        snippet="Mục tiêu thương mại hóa rộng rãi dự kiến quanh mốc 2030.",
    )

    assert doc1.doc_id == doc2.doc_id
    assert doc1.assigned_number == 1
    assert doc2.assigned_number == 1
    # Check that both snippets were recorded under the same document
    assert len(doc1.snippets) == 2
    assert "2026 tại Aichi" in doc1.snippets[0]
    assert "2030" in doc1.snippets[1]


def test_multiple_distinct_documents_receive_sequential_numbers():
    registry = CitationRegistry()

    doc_a = registry.register_source(
        url="https://global.toyota/en/battery",
        title="Toyota Briefing",
        snippet="Toyota excerpt",
    )
    doc_b = registry.register_source(
        url="https://catl.com/solid-state",
        title="CATL Progress",
        snippet="CATL excerpt 500 Wh/kg",
    )
    doc_c = registry.register_source(
        url="https://bnef.com/economics",
        title="Bloomberg NEF",
        snippet="Chi phí gấp 3-5 lần",
    )

    assert doc_a.assigned_number == 1
    assert doc_b.assigned_number == 2
    assert doc_c.assigned_number == 3

    ordered = registry.get_all_ordered()
    assert len(ordered) == 3
    assert [d.assigned_number for d in ordered] == [1, 2, 3]


def test_citation_dictionary_serialization():
    registry = CitationRegistry()
    registry.register_source(
        url="https://nature.com/paper1",
        title="Nature Paper",
        snippet="Verbatim quote",
        year=2025,
    )
    cite_dict = registry.to_citation_dict()

    assert "1" in cite_dict
    assert cite_dict["1"]["id"] == 1
    assert cite_dict["1"]["number"] == 1
    assert cite_dict["1"]["snippet"] == "Verbatim quote"
    assert cite_dict["1"]["verified"] is True


def test_parse_sources_from_research_notes():
    notes = [
        "- Toyota lên kế hoạch sản xuất thử nghiệm ([https://global.toyota/en/battery]) tại Aichi.",
        "- CATL đạt mốc 500 Wh/kg trong phòng thử nghiệm [CATL Report](https://catl.com/lab-report).",
        "- Bổ sung: Toyota cũng đang đánh giá sulfide ([https://www.global.toyota/en/battery/]).",
    ]

    registry = parse_sources_from_research_notes(notes)
    ordered = registry.get_all_ordered()

    # Toyota should only appear once (deduplicated)
    assert len(ordered) == 2
    assert ordered[0].assigned_number == 1
    assert "global.toyota" in ordered[0].url
    assert ordered[1].assigned_number == 2
    assert "catl.com" in ordered[1].url
