"""Observation Density Filter and Domain Authority Scorer for the Harness Guard Layer.

Enforces SWE-agent / OpenHands Action-Observation constraints:
1. Filters out 100% of Tier C spam/dictionary/aggregator domains.
2. Prioritizes Tier A academic, technical, and primary sources.
3. Chunks and condenses observation text (600-800 chars) to prevent consumer GPU VRAM starvation.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from infra.harness.protocol import ObservationSnippet

# Tier A: High-authority academic, technical, and primary research repositories (Score: 1.0)
TIER_A_DOMAINS = {
    "arxiv.org",
    "biorxiv.org",
    "medrxiv.org",
    "github.com",
    "paperswithcode.com",
    "huggingface.co",
    "epoch.ai",
    "openreview.net",
    "semanticscholar.org",
    "nature.com",
    "sciencedirect.com",
    "ieee.org",
    "acm.org",
    "springer.com",
    "pnas.org",
    "cell.com",
    "thegradient.pub",
    "distill.pub",
    "mit.edu",
    "stanford.edu",
    "berkeley.edu",
    "harvard.edu",
    "ox.ac.uk",
    "cam.ac.uk",
    "nih.gov",
    "ncbi.nlm.nih.gov",
}

# Tier C: Zero-authority spam, dictionary endpoints, doc paywalls, and social/video fluff (Score: 0.0)
TIER_C_SPAM_SUBSTRINGS = (
    # Dictionaries & vocab definition endpoints
    "merriam-webster.com",
    "dictionary.com",
    "thesaurus.com",
    "oxfordlearnersdictionaries.com",
    "cambridge.org/dictionary",
    "collinsdictionary.com",
    "tudien",
    "tu-dien",
    "tratu",
    "vocabulary.com",
    # Document sharing & course notes paywalls
    "123doc",
    "studocu.com",
    "tailieu.vn",
    "docplayer.net",
    "scribd.com",
    "coursehero.com",
    "vietjack.com",
    "loigiaihay.com",
    # SEO content farms & generic HR/marketing fluff
    "page1.vn",
    "linkpower.vn",
    "topcv.vn",
    "timviec365",
    # Video streaming & pure social media feeds
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "vimeo.com",
    "dailymotion.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    # Ecommerce & shopping listings
    "shopee.vn",
    "lazada.vn",
    "tiki.vn",
    "amazon.com",
    "aliexpress.com",
)

# Tag / category / topic aggregator URL path patterns that lack substance
AGGREGATOR_PATH_PATTERNS = [
    "/hashtag/",
    "/tag/",
    "/tags/",
    "/category/",
    "/chu-de/",
    "/topic/",
    "/topics/",
]


def score_domain_authority(url: str) -> float:
    """Scores a URL domain authority:

    - Tier A: 1.0 (academic, research papers, core repositories)
    - Tier B: 0.7 (standard credible articles, tech blogs, official docs)
    - Tier C: 0.0 (spam, dictionaries, paywalls, aggregators, video feeds)
    """
    if not url or not isinstance(url, str):
        return 0.0

    clean_url = url.strip().lower()

    # Fast rejection for empty or non-http protocols
    if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        return 0.0

    # 1. Tier C Check: Spam, dictionaries, video, or social media
    for spam_pat in TIER_C_SPAM_SUBSTRINGS:
        if spam_pat in clean_url:
            return 0.0

    # Check for empty aggregator paths
    for agg_pat in AGGREGATOR_PATH_PATTERNS:
        if agg_pat in clean_url:
            return 0.0

    # 2. Extract hostname and check for Tier A
    try:
        parsed = urlparse(clean_url)
        hostname = parsed.hostname or ""
    except Exception:
        return 0.0

    # Match Tier A domains or subdomains (e.g. "raw.githubusercontent.com", "math.stanford.edu")
    for tier_a in TIER_A_DOMAINS:
        if hostname == tier_a or hostname.endswith("." + tier_a):
            return 1.0

    # 3. Default credible Tier B source
    return 0.7


def is_spam_domain(url: str) -> bool:
    """Returns True if the URL belongs to Tier C spam, dictionary, or video endpoints."""
    return score_domain_authority(url) == 0.0


def _truncate_cleanly(text: str, max_chars: int) -> str:
    """Truncate text to max_chars without cutting mid-sentence if possible."""
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    # Try finding the last sentence boundary ('. ', '\n', '? ', '! ')
    last_period = max(
        truncated.rfind(". "),
        truncated.rfind(".\n"),
        truncated.rfind("\n"),
        truncated.rfind("? "),
        truncated.rfind("! "),
    )
    if last_period > int(max_chars * 0.6):
        return truncated[:last_period + 1].strip()

    return truncated.rstrip() + "..."


def filter_and_rank_snippets(
    results: list,
    query: str = "",
    max_snippets: int = 3,
    max_chars_per_snippet: int = 800,
) -> list[ObservationSnippet]:
    """Filter, rank, and condense search result snippets into high-density observations.

    1. Discards 100% of Tier C spam/dictionary/video URLs.
    2. Prioritizes Tier A academic sources and high-density keyword matches.
    3. Condenses raw text into 600-800 characters, safeguarding local GPU VRAM.
    """
    if not results:
        return []

    query_tokens = {
        w.lower()
        for w in re.findall(r"\b\w{3,}\b", query)
    } if query else set()

    candidates: list[ObservationSnippet] = []

    for item in results:
        url = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else "")
        title = getattr(item, "title", None) or (item.get("title") if isinstance(item, dict) else "")
        content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else "")
        published_date = getattr(item, "published_date", None) or (item.get("published_date") if isinstance(item, dict) else None)

        if not url or not content:
            continue

        authority = score_domain_authority(url)
        if authority == 0.0:
            # Strictly drop Tier C spam
            continue

        domain_tier = "tier_a" if authority == 1.0 else "tier_b"

        # Calculate keyword match density
        content_lower = content.lower()
        title_lower = title.lower()
        matches = 0
        for token in query_tokens:
            if token in title_lower:
                matches += 2
            elif token in content_lower:
                matches += 1

        density_bonus = min(0.3, matches * 0.05)
        combined_score = round(authority + density_bonus, 3)

        # Condense content
        clean_content = _truncate_cleanly(content.strip(), max_chars=max_chars_per_snippet)

        candidates.append(
            ObservationSnippet(
                title=title.strip(),
                url=url.strip(),
                content=clean_content,
                domain_tier=domain_tier,
                authority_score=authority,
                density_score=combined_score,
                published_date=published_date,
            )
        )

    # Sort descending by density_score (Tier A with matches first)
    candidates.sort(key=lambda s: s.density_score, reverse=True)

    return candidates[:max_snippets]
