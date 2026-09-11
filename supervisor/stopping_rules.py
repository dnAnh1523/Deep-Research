"""Stopping rules for the supervisor loop."""

from dataclasses import dataclass


@dataclass
class LoopBudget:
    """Budget limits for the supervisor research loop.

    Attributes:
        max_rounds: Maximum number of supervisor rounds (default: 3).
        max_researchers_total: Total maximum number of researchers spawned across all rounds (default: 12).
    """

    max_rounds: int = 3
    max_researchers_total: int = 12


def should_force_stop(
    *, current_round: int, total_researchers_spawned: int, budget: LoopBudget
) -> tuple[bool, str | None]:
    """Check if the supervisor loop must be forcibly stopped based on budget constraints.

    Conditions (evaluated independently):
    1. current_round >= budget.max_rounds -> stop reason must mention "vòng".
    2. total_researchers_spawned >= budget.max_researchers_total -> stop reason must mention "researcher".

    Returns:
        tuple[bool, str | None]: (should_stop, reason). Reason is None if should_stop is False.
    """
    reasons: list[str] = []

    if current_round >= budget.max_rounds:
        reasons.append(
            f"Đã đạt số vòng tối đa ({current_round}/{budget.max_rounds} vòng)."
        )

    if total_researchers_spawned >= budget.max_researchers_total:
        reasons.append(
            f"Đã đạt số researcher tối đa ({total_researchers_spawned}/{budget.max_researchers_total} researcher)."
        )

    if reasons:
        return True, " ".join(reasons)

    return False, None
