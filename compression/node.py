"""Compression node function.

Synthesizes and compresses raw findings into high-density notes.
Makes at most 1 call to LLMProvider.complete().
"""

import re
from infra.interfaces import LLMProvider
from state.schema import AgentState


def _clean_text(text: str) -> str:
    """Defensively clean thinking tags from LLM output."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"</think>", "", cleaned)
    return cleaned.strip()


async def compression_node(
    state: AgentState,
    *,
    llm: LLMProvider | None = None,
) -> dict:
    """Compress new findings into supervisor compressed_notes while preserving evidence and source URLs.

    At most 1 call to LLMProvider.complete().
    """
    sup_state = dict(state.get("supervisor", {}))
    existing_notes = list(sup_state.get("compressed_notes", []))
    raw_findings = list(state.get("raw_findings", []))

    if llm is not None:
        if raw_findings:
            findings_str = "\n\n".join(f"Finding:\n{f[:1500]}" for f in raw_findings)
            existing_str = "\n".join(f"- {n}" for n in existing_notes[-10:])
            prompt = f"""<system_instructions>
You are an information synthesis and compression specialist.
Synthesize and deduplicate findings into dense, high-signal research notes.
CRITICAL: Preserve key facts, metrics, and associated source URLs (e.g. ([URL])) so citations remain verifiable.
Output a bulleted list of dense, self-contained notes.
</system_instructions>

<existing_notes>
{existing_str or 'None'}
</existing_notes>

<new_findings>
{findings_str}
</new_findings>"""
        elif existing_notes:
            notes_str = "\n".join(f"- {n}" for n in existing_notes[-10:])
            prompt = f"""<system_instructions>
You are an information synthesis specialist. Deduplicate and condense the notes below while strictly preserving key metrics and source URLs.
</system_instructions>

<existing_notes>
{notes_str}
</existing_notes>"""
        else:
            prompt = "Synthesize an empty set of research notes into a brief summary."

        response = await llm.complete(prompt=prompt)
        cleaned_response = _clean_text(response.content or "")
        new_items = [
            line.strip("- *").strip()
            for line in cleaned_response.split("\n")
            if line.strip() and len(line.strip()) > 10
        ]
        sup_state["compressed_notes"] = existing_notes + (new_items or [cleaned_response])
    elif raw_findings:
        sup_state["compressed_notes"] = existing_notes + [f[:400] for f in raw_findings]

    return {"supervisor": sup_state}

