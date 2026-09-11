"""Verification node function.

Dual-layer citation verification:
- Layer 1: Entailment check on notes/claims with LLMProvider (at most 1 call).
- Layer 2: Independence check & duplicate grouping using Module 1 (verification.dedup).
"""

from infra.interfaces import LLMProvider
from state.schema import AgentState
from verification.dedup import (
    Source,
    count_independent_sources,
    group_likely_duplicates,
)


async def verification_node(
    state: AgentState,
    *,
    llm: LLMProvider | None = None,
    sources: list[Source] | None = None,
) -> dict:
    """Verify citations and assertions across two distinct validation layers.

    Layer 1: LLM entailment verification (at most 1 call to LLMProvider.complete()).
    Layer 2: Source independence and deduplication via Module 1 domain logic.
    """
    sources_to_verify = sources or []

    # Layer 2: Module 1 domain logic functions
    independent_count = count_independent_sources(sources_to_verify)
    duplicate_groups = group_likely_duplicates(sources_to_verify)

    sup_state = dict(state.get("supervisor", {}))
    notes = sup_state.get("compressed_notes", [])

    entailment_result = "unchecked"
    # Layer 1: Entailment check via LLM (at most 1 call)
    if llm is not None and notes:
        import re
        notes_str = "\n".join(f"- {n}" for n in notes)
        prompt = f"""<system_instructions>
You are a research verification specialist.
Evaluate whether the research claims in the notes below are factually consistent and substantiated by evidence.
Provide a concise verification assessment (e.g., VERIFIED, PARTIALLY_VERIFIED, or UNVERIFIED with a brief 1-sentence note).
</system_instructions>

<research_notes>
{notes_str}
</research_notes>

<independent_sources_count>
{independent_count}
</independent_sources_count>"""
        response = await llm.complete(prompt=prompt)
        raw = (response.content or "").strip()
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        if "<think>" in cleaned:
            cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
        entailment_result = cleaned.strip()


    verification_metadata = {
        "independent_sources_count": independent_count,
        "duplicate_groups_count": len(duplicate_groups),
        "entailment_status": entailment_result,
    }

    return {
        "supervisor": sup_state,
        "verification_metadata": verification_metadata,
    }
