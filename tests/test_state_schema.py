"""Tests for state.schema."""

import typing
from research_brief.validation import ResearchBrief
from state.schema import AgentState, ResearcherState, SupervisorState


def test_states_are_typed_dict_not_pydantic():
    # Verify issubclass of dict and is a TypedDict
    assert issubclass(ResearcherState, dict)
    assert issubclass(SupervisorState, dict)
    assert issubclass(AgentState, dict)

    assert typing.is_typeddict(ResearcherState)
    assert typing.is_typeddict(SupervisorState)
    assert typing.is_typeddict(AgentState)


def test_researcher_state_isolation_and_fields():
    hints = typing.get_type_hints(ResearcherState)
    expected_fields = {"topic", "findings", "tool_calls_made", "status"}
    assert set(hints.keys()) == expected_fields

    # Verify no leaked fields referencing other researchers
    for field_name in hints.keys():
        assert "peer" not in field_name.lower()
        assert "other" not in field_name.lower()
        assert "pool" not in field_name.lower()

    # Verify status is Literal["in_progress", "complete"]
    status_type = hints["status"]
    assert typing.get_origin(status_type) is typing.Literal
    assert set(typing.get_args(status_type)) == {"in_progress", "complete"}

    # Verify instantiating valid ResearcherState
    state: ResearcherState = {
        "topic": "Quantization in LLMs",
        "findings": ["Finding 1", "Finding 2"],
        "tool_calls_made": 3,
        "status": "in_progress",
    }
    assert state["status"] == "in_progress"


def test_supervisor_state_fields_and_types():
    hints = typing.get_type_hints(SupervisorState)
    expected_fields = {
        "brief",
        "compressed_notes",
        "current_round",
        "researchers_spawned_total",
        "status",
    }
    assert set(hints.keys()) == expected_fields
    assert hints["brief"] is ResearchBrief

    # Verify status is Literal["delegating", "writing_report", "done"]
    status_type = hints["status"]
    assert typing.get_origin(status_type) is typing.Literal
    assert set(typing.get_args(status_type)) == {
        "delegating",
        "writing_report",
        "done",
    }

    brief = ResearchBrief(
        objective="Analyze LLM pruning techniques",
        sub_questions=["What is unstructured pruning?"],
        constraints=[],
    )
    sup_state: SupervisorState = {
        "brief": brief,
        "compressed_notes": ["Note 1"],
        "current_round": 1,
        "researchers_spawned_total": 2,
        "status": "delegating",
    }
    assert sup_state["current_round"] == 1


def test_agent_state_fields_and_nullable_final_report():
    hints = typing.get_type_hints(AgentState)
    expected_fields = {
        "thread_id",
        "user_query",
        "clarification_history",
        "supervisor",
        "final_report",
    }
    assert set(hints.keys()) == expected_fields
    assert hints["supervisor"] is SupervisorState

    # Verify final_report is str | None (Union[str, NoneType])
    final_report_type = hints["final_report"]
    origin = typing.get_origin(final_report_type)
    args = typing.get_args(final_report_type)
    assert type(None) in args
    assert str in args

    # Can instantiate with final_report=None
    brief = ResearchBrief(objective="Test", sub_questions=["Q1"], constraints=[])
    agent_state_none: AgentState = {
        "thread_id": "session_123",
        "user_query": "Explain LLM distillation",
        "clarification_history": [],
        "supervisor": {
            "brief": brief,
            "compressed_notes": [],
            "current_round": 0,
            "researchers_spawned_total": 0,
            "status": "delegating",
        },
        "final_report": None,
    }
    assert agent_state_none["final_report"] is None

    # Can instantiate with final_report as string
    agent_state_done: AgentState = {
        "thread_id": "session_123",
        "user_query": "Explain LLM distillation",
        "clarification_history": [],
        "supervisor": {
            "brief": brief,
            "compressed_notes": ["Done"],
            "current_round": 1,
            "researchers_spawned_total": 1,
            "status": "done",
        },
        "final_report": "# Comprehensive Report on Distillation...",
    }
    assert isinstance(agent_state_done["final_report"], str)
