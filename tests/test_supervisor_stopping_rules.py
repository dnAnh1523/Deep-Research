"""Tests for supervisor.stopping_rules."""

from supervisor.stopping_rules import LoopBudget, should_force_stop


def test_loop_budget_defaults():
    budget = LoopBudget()
    assert budget.max_rounds == 3
    assert budget.max_researchers_total == 12


def test_stop_when_max_rounds_reached():
    budget = LoopBudget(max_rounds=3, max_researchers_total=12)
    should_stop, reason = should_force_stop(
        current_round=3,
        total_researchers_spawned=5,
        budget=budget,
    )
    assert should_stop is True
    assert reason is not None
    assert "vòng" in reason.lower()


def test_stop_when_max_researchers_reached_even_if_current_round_is_low():
    budget = LoopBudget(max_rounds=3, max_researchers_total=12)
    # round is only 1, but spawned 12 researchers
    should_stop, reason = should_force_stop(
        current_round=1,
        total_researchers_spawned=12,
        budget=budget,
    )
    assert should_stop is True
    assert reason is not None
    assert "researcher" in reason.lower()


def test_no_stop_when_under_budget():
    budget = LoopBudget(max_rounds=3, max_researchers_total=12)
    should_stop, reason = should_force_stop(
        current_round=2,
        total_researchers_spawned=8,
        budget=budget,
    )
    assert should_stop is False
    assert reason is None
