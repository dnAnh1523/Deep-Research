"""Supervisor node function.

Orchestrates research rounds, deciding whether to delegate more research workers
or proceed to report generation.
Must call should_force_stop() from Module 1.
Makes at most 1 call to LLMProvider.complete().
"""

import re
from infra.harness import format_hermes_tool_definition, validate_and_repair_decision
from infra.interfaces import LLMProvider
from infra.temporal import get_temporal_context
from state.schema import AgentState
from supervisor.stopping_rules import LoopBudget, should_force_stop


def _clean_text(text: str) -> str:
    """Defensively clean thinking tags from LLM output."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"</think>", "", cleaned)
    return cleaned.strip()


async def supervisor_node(
    state: AgentState,
    *,
    llm: LLMProvider | None = None,
    budget: LoopBudget | None = None,
) -> dict:
    """Coordinate research loop and enforce stopping rules with Gap Analysis and dynamic query generation.

    Acceptance criteria:
    - Node nào cần quyết định "dừng hay tiếp tục" phải gọi hàm từ Module 1, không tự viết điều kiện if/else riêng.
    - Không quá 1 lệnh gọi LLMProvider.complete() mỗi lần chạy node.
    """
    if budget is None:
        budget = LoopBudget()

    sup_state = dict(state.get("supervisor", {}))
    current_round = sup_state.get("current_round", 0)
    total_spawned = sup_state.get("researchers_spawned_total", 0)

    # MANDATORY: Delegate stopping decision to Module 1
    must_stop, reason = should_force_stop(
        current_round=current_round,
        total_researchers_spawned=total_spawned,
        budget=budget,
    )

    if must_stop:
        # Stop condition reached: advance directly to writing report without LLM call (0 calls <= 1)
        sup_state["status"] = "writing_report"
        return {"supervisor": sup_state}

    # At most 1 call to LLMProvider.complete() to evaluate coverage and plan delegation
    if llm is not None:
        brief = sup_state.get("brief")
        notes = sup_state.get("compressed_notes", [])
        sub_questions = getattr(brief, "sub_questions", []) or []
        objective = getattr(brief, "objective", "") or ""
        if sub_questions:
            sub_q_checklist = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(sub_questions))
        else:
            sub_q_checklist = f"1. {objective or 'Address the central inquiry'}"

        tools_def = format_hermes_tool_definition()
        temporal_xml = get_temporal_context().format_temporal_anchor_xml()

        prompt = f"""<system_instructions>
You are an expert research supervisor coordinating an autonomous multi-worker research process.
Your responsibility is to critically evaluate whether the collected research notes sufficiently address the research checklist.

{temporal_xml}

{tools_def}

Protocol Guidelines (Schema-Enforced Tool Protocol):
CRITICAL: Always start by thinking inside <thought>...</thought>.
Then wrap your structured action inside <tool_call>...</tool_call>. DO NOT output bare JSON at the root level.

1. First, think step-by-step inside <thought>...</thought> analyzing checklist coverage vs collected notes.
2. If all checklist questions are answered with concrete data and solid arguments:
   <tool_call>
   {{"name": "conclude_research", "arguments": {{"completion_rationale": "..."}}}}
   </tool_call>
3. If a genuine gap exists for an unanswered checklist question:
   <tool_call>
   {{"name": "delegate_research_queries", "arguments": {{"gap_analysis": "...", "queries": [...]}}}}
   </tool_call>
   Or alternately provide structured text:
     GAP: <1-sentence description of missing evidence>
     QUERIES:
     - <targeted search query addressing that specific unanswered question>

Respond in the language of the research objective.
</system_instructions>

<research_objective>
{objective}
</research_objective>

<research_checklist>
{sub_q_checklist}
</research_checklist>

<collected_notes>
{notes if notes else 'No notes collected yet.'}
</collected_notes>"""
        response = await llm.complete(prompt=prompt)
        eval_text = _clean_text(response.content or "")

        decision = validate_and_repair_decision(eval_text, default_anchor=objective)

        if decision.is_completed:
            sup_state["status"] = "writing_report"
            if decision.synthesis_notes:
                sup_state["research_guidance"] = decision.synthesis_notes
            return {"supervisor": sup_state}

        follow_ups = [q.to_search_query() for q in decision.queries if q.to_search_query()]
        sup_state["research_guidance"] = decision.gap_analysis or decision.thought or eval_text
        if follow_ups:
            sup_state["follow_up_queries"] = follow_ups

    sup_state["current_round"] = current_round + 1
    sup_state["status"] = "delegating"
    return {"supervisor": sup_state}

