"""Temporal Grounding Provider.

Provides normalized system clock context, calendar date representations,
and temporal query anchoring to eliminate temporal blindness in open-weight models.
Clean Architecture: Pure Python stdlib datetime, zero external network dependencies.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import re


VIETNAMESE_WEEKDAYS = {
    0: "Thứ Hai",
    1: "Thứ Ba",
    2: "Thứ Tư",
    3: "Thứ Năm",
    4: "Thứ Sáu",
    5: "Thứ Bảy",
    6: "Chủ Nhật",
}


@dataclass(frozen=True)
class TemporalContext:
    """Normalized temporal context container.

    Attributes:
        current_date_iso: YYYY-MM-DD formatted string (e.g. '2026-09-09').
        current_date_human: English human-readable date (e.g. 'Wednesday, September 09, 2026').
        current_date_vietnamese: Vietnamese date representation.
        current_year: Calendar year integer (e.g. 2026).
        recent_years_window: Window of current and immediate previous year (e.g. '2025-2026').
    """

    current_date_iso: str
    current_date_human: str
    current_date_vietnamese: str
    current_year: int
    recent_years_window: str

    def format_temporal_anchor_xml(self) -> str:
        """Format canonical XML block for system prompt injection."""
        return (
            f"<current_temporal_anchor>\n"
            f"Current Date: {self.current_date_human} ({self.current_date_iso})\n"
            f"Current Year: {self.current_year}\n"
            f"Temporal Baseline: {self.recent_years_window}\n"
            f"Instructions on Time Awareness:\n"
            f"1. Your pre-training knowledge has a historical cutoff date. Any inquiry about 'now', 'currently', 'recent', 'latest', or 'năm nay' refers strictly to the contemporary context of {self.current_year}.\n"
            f"2. Prioritize verified live facts retrieved via web search over pre-training memory for any contemporary metrics, policies, or developments.\n"
            f"3. Always ground time-sensitive statements with concrete dates or years (e.g., 'tính đến năm {self.current_year}', 'trong giai đoạn {self.recent_years_window}') rather than ambiguous relative terms like 'hiện nay'.\n"
            f"</current_temporal_anchor>"
        )


def get_temporal_context(override_date: datetime | None = None) -> TemporalContext:
    """Return normalized temporal context.

    Args:
        override_date: Optional datetime for deterministic testing or custom simulation.
    """
    dt = override_date or datetime.now()
    year = dt.year
    iso_date = dt.strftime("%Y-%m-%d")
    human_date = dt.strftime("%A, %B %d, %Y")
    
    vn_day = VIETNAMESE_WEEKDAYS.get(dt.weekday(), "Ngày")
    vn_date = f"{vn_day}, ngày {dt.day:02d} tháng {dt.month:02d} năm {year}"
    recent_window = f"{year - 1}-{year}"

    return TemporalContext(
        current_date_iso=iso_date,
        current_date_human=human_date,
        current_date_vietnamese=vn_date,
        current_year=year,
        recent_years_window=recent_window,
    )


# Relative temporal keywords in Vietnamese and English
TEMPORAL_RELATIVE_PATTERNS = [
    r"\bmới nhất\b",
    r"\bhiện nay\b",
    r"\bhiện tại\b",
    r"\bgần đây\b",
    r"\bnăm nay\b",
    r"\bxu hướng mới\b",
    r"\blatest\b",
    r"\bcurrent\b",
    r"\brecent\b",
    r"\btrends\b",
    r"\bstate of the art\b",
    r"\bsota\b",
]

_YEAR_REGEX = re.compile(r"\b(19\d\d|20\d\d)\b")


def anchor_query_with_temporal_context(
    query: str,
    context: TemporalContext | None = None,
) -> str:
    """Enhance relative temporal queries by anchoring with the current calendar year.

    If the query contains relative temporal terms ('mới nhất', 'hiện nay', 'latest', etc.)
    and does not already contain an explicit 4-digit calendar year, appends the current year.
    """
    cleaned_q = query.strip()
    if not cleaned_q:
        return cleaned_q

    # If query already contains a 4-digit year (e.g., 2024, 2025, 2026), leave as-is
    if _YEAR_REGEX.search(cleaned_q):
        return cleaned_q

    # Check if query contains any relative temporal keyword
    has_relative_term = any(
        re.search(pat, cleaned_q, re.IGNORECASE) for pat in TEMPORAL_RELATIVE_PATTERNS
    )

    if has_relative_term:
        ctx = context or get_temporal_context()
        return f"{cleaned_q} {ctx.current_year}"

    return cleaned_q
