"""State schemas for the deep research agent across graph execution tiers.

Follows the 3-tier ephemeral state model:
1. AgentState: Global state across the entire user session.
2. SupervisorState: Coordination state managing rounds and researchers.
3. ResearcherState: Isolated state for individual concurrent research workers.
"""

from typing import Literal, TypedDict
from research_brief.validation import ResearchBrief


class ResearcherState(TypedDict):
    """Isolated state for a single researcher worker.

    Must NOT contain any reference to other researchers or global coordination state
    to prevent race conditions during parallel fan-out execution.
    """

    topic: str
    findings: list[str]
    tool_calls_made: int
    status: Literal["in_progress", "complete"]


class SupervisorState(TypedDict):
    """State for the supervisor loop orchestrating research workers."""

    brief: ResearchBrief
    compressed_notes: list[str]
    current_round: int
    researchers_spawned_total: int
    status: Literal["delegating", "writing_report", "done"]


class AgentState(TypedDict):
    """Top-level agent state spanning the full lifecycle of a research request."""

    thread_id: str
    user_query: str
    clarification_history: list[str]
    supervisor: SupervisorState
    final_report: str | None
