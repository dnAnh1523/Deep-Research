"""Harness Guard Layer for Deep Research Agent.

Synthesizes:
1. Nous Research Hermes Agent Schema-Enforced Tool Protocol (SETP) & XML Envelopes.
2. DeepSeek Reasoning & Evaluation Harness Rule-Based Verifiers and Information Gain (ΔI).
3. Princeton SWE-agent & OpenHands ACI Action-Observation density filtering and stagnation breaking.
"""

from infra.harness.convergence import (
    StagnationDetector,
    calculate_information_gain,
)
from infra.harness.linter import (
    FORBIDDEN_META_PATTERNS,
    generate_synthetic_error,
    sanitize_aspect_query,
    validate_and_repair_decision,
)
from infra.harness.observation_filter import (
    TIER_A_DOMAINS,
    TIER_C_SPAM_SUBSTRINGS,
    filter_and_rank_snippets,
    is_spam_domain,
    score_domain_authority,
)
from infra.harness.protocol import (
    ObservationSnippet,
    ResearchQueryAction,
    SupervisorDecision,
    extract_hermes_blocks,
    format_hermes_tool_definition,
)

__all__ = [
    # Protocol
    "ResearchQueryAction",
    "SupervisorDecision",
    "ObservationSnippet",
    "format_hermes_tool_definition",
    "extract_hermes_blocks",
    # Linter
    "FORBIDDEN_META_PATTERNS",
    "sanitize_aspect_query",
    "validate_and_repair_decision",
    "generate_synthetic_error",
    # Observation Filter
    "TIER_A_DOMAINS",
    "TIER_C_SPAM_SUBSTRINGS",
    "score_domain_authority",
    "is_spam_domain",
    "filter_and_rank_snippets",
    # Convergence
    "calculate_information_gain",
    "StagnationDetector",
]
