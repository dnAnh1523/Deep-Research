"""Tests for research_brief.validation."""

import pytest
from research_brief.validation import ResearchBrief, validate_brief


def test_valid_brief_passes():
    brief = ResearchBrief(
        objective="Tìm hiểu các phương pháp lượng tử hoá mô hình LLM",
        sub_questions=[
            "Post-training quantization (PTQ) hoạt động ra sao?",
            "Quantization-aware training (QAT) có ưu nhược điểm gì?",
        ],
        constraints=["Chỉ tập trung vào mô hình open-source"],
    )
    is_valid, errors = validate_brief(brief)
    assert is_valid is True
    assert errors == []


@pytest.mark.parametrize("empty_objective", ["", "   ", "\t\n  "])
def test_empty_or_whitespace_objective_fails(empty_objective: str):
    brief = ResearchBrief(
        objective=empty_objective,
        sub_questions=["Câu hỏi 1"],
        constraints=[],
    )
    is_valid, errors = validate_brief(brief)
    assert is_valid is False
    assert len(errors) > 0
    # Error message must mention 'objective'
    assert any("objective" in err.lower() for err in errors)


def test_zero_sub_questions_fails():
    brief = ResearchBrief(
        objective="Mục tiêu nghiên cứu hợp lệ",
        sub_questions=[],
        constraints=[],
    )
    is_valid, errors = validate_brief(brief)
    assert is_valid is False
    assert len(errors) > 0
    assert any("sub_questions" in err.lower() or "câu hỏi" in err.lower() for err in errors)


def test_more_than_eight_sub_questions_fails():
    brief = ResearchBrief(
        objective="Mục tiêu nghiên cứu hợp lệ",
        sub_questions=[f"Câu hỏi số {i}" for i in range(1, 10)],  # 9 questions
        constraints=[],
    )
    is_valid, errors = validate_brief(brief)
    assert is_valid is False
    assert len(errors) > 0
    # Error message must mention soft ceiling / report quality, not rate limit
    error_text = " ".join(errors)
    assert "chất lượng report" in error_text
    assert "rate limit" in error_text


def test_duplicate_sub_questions_case_and_whitespace_insensitive():
    brief = ResearchBrief(
        objective="Mục tiêu nghiên cứu hợp lệ",
        sub_questions=[
            "So sánh PyTorch và JAX?",
            "  so sánh   pytorch và jax?  ",
        ],
        constraints=[],
    )
    is_valid, errors = validate_brief(brief)
    assert is_valid is False
    assert len(errors) > 0
    # Must list the duplicate question
    error_text = " ".join(errors)
    assert "trùng lặp" in error_text.lower()
    assert "so sánh" in error_text.lower()


def test_invalid_brief_never_returns_empty_errors():
    brief = ResearchBrief(
        objective="",
        sub_questions=[],
        constraints=[],
    )
    is_valid, errors = validate_brief(brief)
    assert is_valid is False
    assert len(errors) > 0
