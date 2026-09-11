"""Researcher worker node function.

Performs targeted web search via SearchClient and analyzes retrieved snippets via LLMProvider.
"""

import re
from infra.harness import filter_and_rank_snippets, score_domain_authority
from infra.interfaces import LLMProvider, SearchClient
from state.schema import ResearcherState


def _clean_text(text: str) -> str:
    """Defensively clean thinking tags from LLM output."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"</think>", "", cleaned)
    return cleaned.strip()


def is_valid_research_url(url: str) -> bool:
    """Filter out video platforms, social networks, and tag/category aggregator URLs."""
    if not url or not isinstance(url, str):
        return False
    return score_domain_authority(url) > 0.0


async def researcher_node(
    state: ResearcherState,
    *,
    llm: LLMProvider | None = None,
    search_client: SearchClient | None = None,
    seen_urls: list[str] | None = None,
) -> dict:
    """Execute research search and content extraction for a single sub-topic with seen_urls filtering and URL hygiene."""
    topic = state.get("topic", "")
    findings = list(state.get("findings", []))
    tool_calls_made = state.get("tool_calls_made", 0)

    # Resolve already seen URLs from parameter or state
    already_seen = set(seen_urls or state.get("seen_urls", []))

    search_results = []
    if search_client is not None:
        # Request up to 5 results so filtering seen_urls still leaves fresh sources
        all_results = await search_client.search(query=topic, max_results=5)
        tool_calls_made += 1

        # First pass: unseen candidates
        unseen_candidates = [
            r for r in all_results
            if getattr(r, "url", "") and r.url not in already_seen
        ]

        # Apply Harness Observation Density Filter (drops Tier C spam, ranks Tier A, condenses text)
        ranked = filter_and_rank_snippets(
            unseen_candidates,
            query=topic,
            max_snippets=3,
            max_chars_per_snippet=800,
        )

        if not ranked and all_results:
            # Fallback if all candidates were seen: rank all available non-spam results
            ranked = filter_and_rank_snippets(
                all_results,
                query=topic,
                max_snippets=2,
                max_chars_per_snippet=800,
            )

        search_results = ranked

    visited_urls = [r.url for r in search_results if hasattr(r, "url") and r.url]

    if llm is not None and search_results:
        snippets = "\n\n".join(
            f"Source [{i + 1}] Title: {r.title}\nURL: {r.url}"
            + (f"\nPublished Date: {getattr(r, 'published_date', None)}" if getattr(r, "published_date", None) else "")
            + f"\nExcerpt: {r.content}"
            for i, r in enumerate(search_results)
        )
        prompt = f"""<system_instructions>
You are an investigative research worker.
Extract concrete facts, quantitative metrics, substantive findings, and diverse viewpoints relevant to the assigned topic.
CRITICAL: Include the source URL in parentheses for each key finding (e.g., "... finding details ([https://...])").
If a source includes a published date, note the timeframe of the evidence.
Respond in the language of the assigned sub-topic.
</system_instructions>

<sub_topic>
{topic}
</sub_topic>

<web_sources>
{snippets}
</web_sources>"""
        response = await llm.complete(prompt=prompt)
        findings.append(_clean_text(response.content or ""))
    elif search_results:
        findings.extend(
            f"[{r.title}]({r.url})"
            + (f" ({getattr(r, 'published_date', '')})" if getattr(r, "published_date", None) else "")
            + f": {r.content}"
            for r in search_results
        )

    return {
        "topic": topic,
        "findings": findings,
        "tool_calls_made": tool_calls_made,
        "status": "complete",
        "visited_urls": visited_urls,
    }


