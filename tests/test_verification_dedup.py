"""Tests for verification.dedup."""

from verification.dedup import (
    Source,
    count_independent_sources,
    group_likely_duplicates,
)


def test_empty_sources():
    assert group_likely_duplicates([]) == []
    assert count_independent_sources([]) == 0


def test_domain_matching_ignores_www_prefix():
    s1 = Source(url="https://www.example.com/article", title="Machine Learning Overview")
    s2 = Source(url="https://example.com/article2", title="Machine Learning Overview")

    groups = group_likely_duplicates([s1, s2])
    assert len(groups) == 1
    assert groups[0] == [s1, s2]
    assert count_independent_sources([s1, s2]) == 1


def test_title_matching_normalizes_case_and_collapsed_whitespace():
    s1 = Source(url="https://ai.org/paper", title="Deep   Research   Agents  ")
    s2 = Source(url="https://ai.org/paper-mirror", title="deep research agents")

    groups = group_likely_duplicates([s1, s2])
    assert len(groups) == 1
    assert groups[0] == [s1, s2]
    assert count_independent_sources([s1, s2]) == 1


def test_different_domains_are_always_independent_even_with_identical_title():
    s1 = Source(url="https://nyt.com/story1", title="AI Breakthrough in 2026")
    s2 = Source(url="https://theverge.com/story2", title="AI Breakthrough in 2026")

    groups = group_likely_duplicates([s1, s2])
    # Must be 2 separate groups because domains are different
    assert len(groups) == 2
    assert count_independent_sources([s1, s2]) == 2


def test_same_domain_different_titles_and_paths_are_independent():
    s1 = Source(url="https://arxiv.org/abs/2301.00001", title="Paper A")
    s2 = Source(url="https://arxiv.org/abs/2301.00002", title="Paper B")

    groups = group_likely_duplicates([s1, s2])
    assert len(groups) == 2
    assert count_independent_sources([s1, s2]) == 2


def test_same_domain_same_url_different_title_are_grouped():
    s1 = Source(url="https://arxiv.org/abs/2301.00001", title="Paper A Initial Draft")
    s2 = Source(url="https://www.arxiv.org/abs/2301.00001", title="Paper A Final Revised")

    groups = group_likely_duplicates([s1, s2])
    assert len(groups) == 1
    assert count_independent_sources([s1, s2]) == 1


def test_count_independent_sources_returns_number_of_groups():
    # 4 sources:
    # - Group 1: 2 sources on example.com with identical title
    # - Group 2: 1 source on example.com with distinct title & path
    # - Group 3: 1 source on other.com with identical title to Group 1
    s1 = Source(url="https://example.com/p1", title="Common Topic")
    s2 = Source(url="https://www.example.com/p2", title="  common   topic  ")
    s3 = Source(url="https://example.com/p3", title="Unique Topic")
    s4 = Source(url="https://other.com/p1", title="Common Topic")

    sources = [s1, s2, s3, s4]
    groups = group_likely_duplicates(sources)
    assert len(groups) == 3
    assert count_independent_sources(sources) == 3
