"""Verification domain module."""

from verification.dedup import (
    Source,
    count_independent_sources,
    group_likely_duplicates,
)

__all__ = ["Source", "count_independent_sources", "group_likely_duplicates"]
