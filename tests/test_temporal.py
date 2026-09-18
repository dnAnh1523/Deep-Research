"""Unit tests for infra.temporal (Temporal Grounding Layer)."""

import ast
from datetime import datetime
from pathlib import Path
import pytest
from infra.harness import ResearchQueryAction
from infra.temporal import (
    TemporalContext,
    anchor_query_with_temporal_context,
    get_temporal_context,
)


def test_temporal_context_generation_and_override():
    """Verify TemporalContext properly parses and normalizes datetime representations."""
    test_dt = datetime(2026, 9, 9, 10, 30, 0)
    ctx = get_temporal_context(override_date=test_dt)

    assert ctx.current_year == 2026
    assert ctx.current_date_iso == "2026-09-09"
    assert ctx.current_date_human == "Wednesday, September 09, 2026"
    assert "Thứ Tư, ngày 09 tháng 09 năm 2026" in ctx.current_date_vietnamese
    assert ctx.recent_years_window == "2025-2026"


def test_format_temporal_anchor_xml():
    """Verify XML block format and essential grounding instructions."""
    test_dt = datetime(2026, 9, 9, 10, 30, 0)
    ctx = get_temporal_context(override_date=test_dt)
    xml = ctx.format_temporal_anchor_xml()

    assert "<current_temporal_anchor>" in xml
    assert "</current_temporal_anchor>" in xml
    assert "Current Date: Wednesday, September 09, 2026 (2026-09-09)" in xml
    assert "Current Year: 2026" in xml
    assert "Temporal Baseline: 2025-2026" in xml
    assert "historical cutoff" in xml


def test_anchor_query_with_temporal_context():
    """Verify automatic appending of current year for relative temporal queries."""
    test_dt = datetime(2026, 9, 9)
    ctx = get_temporal_context(override_date=test_dt)

    # 1. Queries with relative terms and no year -> must append current year
    assert (
        anchor_query_with_temporal_context("tiến độ pin thể rắn mới nhất", context=ctx)
        == "tiến độ pin thể rắn mới nhất 2026"
    )
    assert (
        anchor_query_with_temporal_context("chính sách thuế hiện nay", context=ctx)
        == "chính sách thuế hiện nay 2026"
    )
    assert (
        anchor_query_with_temporal_context("latest solid state battery developments", context=ctx)
        == "latest solid state battery developments 2026"
    )
    assert (
        anchor_query_with_temporal_context("thị trường bất động sản gần đây", context=ctx)
        == "thị trường bất động sản gần đây 2026"
    )

    # 2. Queries that ALREADY contain a 4-digit calendar year -> must NOT append duplicate year
    assert (
        anchor_query_with_temporal_context("báo cáo tài chính mới nhất năm 2024", context=ctx)
        == "báo cáo tài chính mới nhất năm 2024"
    )
    assert (
        anchor_query_with_temporal_context("quy hoạch giao thông 2030", context=ctx)
        == "quy hoạch giao thông 2030"
    )

    # 3. Static/timeless queries without relative terms -> must remain untouched
    assert (
        anchor_query_with_temporal_context("thuật toán Dijkstra tìm đường đi ngắn nhất", context=ctx)
        == "thuật toán Dijkstra tìm đường đi ngắn nhất"
    )
    assert (
        anchor_query_with_temporal_context("nguyên lý hoạt động của biến áp", context=ctx)
        == "nguyên lý hoạt động của biến áp"
    )


def test_research_query_action_temporal_anchoring():
    """Verify ResearchQueryAction.to_search_query() automatically applies temporal grounding."""
    action = ResearchQueryAction(
        subject_anchor="Pin thể rắn",
        technical_aspect="tiến độ công nghệ mới nhất",
    )
    query = action.to_search_query()
    # Query must combine anchor + aspect and anchor with current year
    assert "Pin thể rắn" in query
    assert "tiến độ công nghệ mới nhất" in query
    # Must contain 4-digit year (e.g. 2026)
    assert str(datetime.now().year) in query


def test_clean_architecture_boundaries_infra_temporal():
    """Verify infra/temporal.py imports ONLY stdlib modules, strictly 0 external deps."""
    temporal_file = Path(__file__).resolve().parent.parent / "src" / "infra" / "temporal.py"
    tree = ast.parse(temporal_file.read_text(encoding="utf-8"), filename=str(temporal_file))

    allowed_stdlib = {"dataclasses", "datetime", "re", "typing"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_pkg = alias.name.split(".")[0]
                assert top_pkg in allowed_stdlib, f"Unexpected external import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top_pkg = node.module.split(".")[0]
                assert top_pkg in allowed_stdlib, f"Unexpected external import: {node.module}"
