"""Research brief node function.

Generates a structured ResearchBrief from the user query and clarification history.
Calls validate_brief() from Module 1.
Makes at most 1 call to LLMProvider.complete().
"""

import json
from infra.interfaces import LLMProvider
from infra.temporal import get_temporal_context
from research_brief.validation import ResearchBrief, validate_brief
from state.schema import AgentState


async def research_brief_node(
    state: AgentState,
    *,
    llm: LLMProvider | None = None,
) -> dict:
    """Generate and validate a structured ResearchBrief.

    At most 1 call to LLMProvider.complete().
    Must call validate_brief() from Module 1.
    """
    user_query = state.get("user_query", "")
    clarifications = state.get("clarification_history", [])

    brief: ResearchBrief
    if llm is not None:
        temporal_xml = get_temporal_context().format_temporal_anchor_xml()
        clarifications_str = "\n".join(f"- {c}" for c in clarifications) if clarifications else "None"
        prompt = f"""<system_instructions>
You are an expert research planning specialist.
Decompose the user's research request into a clean, structured research plan.

{temporal_xml}

Principles for Sub-questions:
1. Need-based & Minimal Sizing: Size the number of sub-questions strictly according to the query's intrinsic complexity. For focused or narrow requests, use 1 or a minimal number of questions. Do NOT artificially inflate the list with redundant sub-questions.
2. Orthogonality: Each sub-question must address a distinct, non-overlapping facet or dimension of the topic. Avoid repetition or sub-questions that are mere subsets of one another.
3. Language & Scope: Preserve the primary language, domain context, and any specific entities, timeframes, or geographic boundaries explicitly stated in the query. Only restrict scope if specifically requested by the user.

Return pure JSON with this exact schema:
{{
  "objective": "Concise, precise summary of overall research objective",
  "sub_questions": ["Distinct, non-overlapping sub-question(s) to investigate"],
  "constraints": ["Explicit boundaries, timeframes, or specific constraints if requested by user"]
}}
Output ONLY valid JSON.
</system_instructions>

<user_query>
{user_query}
</user_query>

<clarifications>
{clarifications_str}
</clarifications>"""
        # At most 1 call to LLMProvider.complete()
        response = await llm.complete(prompt=prompt)
        try:
            import re
            raw = response.content.strip()
            # Clean thinking tags if present
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
            if "<think>" in raw:
                raw = re.sub(r"<think>.*", "", raw, flags=re.DOTALL)
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.splitlines()
                raw = "\n".join(
                    lines[1:-1] if lines[-1].startswith("```") else lines[1:]
                )
            data = json.loads(raw.strip())
            brief = ResearchBrief(
                objective=data.get("objective", user_query),
                sub_questions=data.get("sub_questions", [user_query]),
                constraints=data.get("constraints", []),
            )
        except Exception:
            brief = ResearchBrief(
                objective=user_query,
                sub_questions=[f"Detailed investigation of {user_query}"],
                constraints=[],
            )
    else:

        brief = ResearchBrief(
            objective=user_query,
            sub_questions=[f"Detailed investigation of {user_query}"],
            constraints=[],
        )

    # Call domain validation from Module 1
    is_valid, _ = validate_brief(brief)
    if not is_valid:
        # Sanitize if brief has duplicates or exceeds limit
        deduped: list[str] = []
        seen: set[str] = set()
        for q in brief.sub_questions:
            norm = " ".join(q.strip().lower().split())
            if norm and norm not in seen:
                seen.add(norm)
                deduped.append(q)
        if not deduped:
            deduped = [f"Investigation of {user_query}"]
        brief.sub_questions = deduped[:8]
        if not brief.objective or not brief.objective.strip():
            brief.objective = user_query or "Research Investigation"

    current_sup = dict(state.get("supervisor", {}))
    current_sup["brief"] = brief
    return {"supervisor": current_sup}
