"""Validation logic for research briefs."""

from dataclasses import dataclass


@dataclass
class ResearchBrief:
    """Represents a research brief generated before deep research starts."""

    objective: str
    sub_questions: list[str]
    constraints: list[str]


def validate_brief(brief: ResearchBrief) -> tuple[bool, list[str]]:
    """Validate a ResearchBrief according to domain rules.

    Rules:
    - objective must not be empty or whitespace only.
    - sub_questions length must be between 1 and 8 inclusive.
    - sub_questions must not contain duplicates (case-insensitive, whitespace-collapsed).

    Returns:
        tuple[bool, list[str]]: (is_valid, list_of_error_messages)
    """
    errors: list[str] = []

    if not brief.objective or not brief.objective.strip():
        errors.append("Trường 'objective' không được để trống hoặc chỉ chứa khoảng trắng.")

    num_sub_questions = len(brief.sub_questions)
    if num_sub_questions < 1:
        errors.append("Danh sách 'sub_questions' phải có ít nhất 1 câu hỏi.")
    elif num_sub_questions > 8:
        errors.append(
            f"Danh sách 'sub_questions' có {num_sub_questions} câu, vượt quá giới hạn 8 câu. "
            "Đây là trần mềm cho chất lượng report (không phải rate limit)."
        )

    seen_normalized: dict[str, str] = {}
    for q in brief.sub_questions:
        normalized = " ".join(q.strip().lower().split())
        if not normalized:
            continue
        if normalized in seen_normalized:
            errors.append(
                f"Phát hiện câu hỏi phụ trùng lặp: '{q}' (trùng với '{seen_normalized[normalized]}')."
            )
        else:
            seen_normalized[normalized] = q

    if errors:
        return False, errors
    return True, []
