"""Clarify node function.

Engages in clarifying user queries that are ambiguous or underspecified.
Makes at most 1 call to LLMProvider.complete().
"""

from infra.interfaces import LLMProvider
from state.schema import AgentState


async def clarify_node(
    state: AgentState,
    *,
    llm: LLMProvider | None = None,
) -> dict:
    """Assess user query and add clarification question/note if necessary.

    At most 1 LLM call is made.
    """
    user_query = state.get("user_query", "")
    history = list(state.get("clarification_history", []))

    # If already clarified or clearly specified, we don't need additional clarification
    if len(history) >= 2 or len(user_query.split()) > 15:
        return {"clarification_history": history}

    if llm is None:
        return {"clarification_history": history}

    import re

    prompt = f"""<system_instructions>
You are a helpful research assistant.
Assess whether the user's research request is so ambiguous or broad that it requires immediate clarification.
- If clarification is genuinely needed, formulate a single polite, specific question in the user's language.
- If the topic is already self-contained or sufficiently clear, formulate a concise confirmation (e.g. confirming the scope) in the user's language.
Respond with only the single question or confirmation.
</system_instructions>

<user_query>
{user_query}
</user_query>"""
    # At most 1 call to LLMProvider.complete()
    response = await llm.complete(prompt=prompt)
    raw = (response.content or "").strip()
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    clarification = cleaned.strip()

    history.append(clarification)
    return {"clarification_history": history}

