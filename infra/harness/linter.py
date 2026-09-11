"""Pre-flight Linter, Query Sanitizer, and Safe Decision Parser for the Harness Guard Layer.

Eradicates regex split failures (e.g. `split("QUERIES:", 1)`), cleans meta-tokens,
and provides zero-cost local synthetic error reflection.
"""

from __future__ import annotations

import json
import re
from typing import Any

from infra.harness.protocol import (
    ResearchQueryAction,
    SupervisorDecision,
    extract_hermes_blocks,
)

# Common forbidden metadata prefixes emitted by LLMs when instructed to output queries
FORBIDDEN_META_PATTERNS = [
    re.compile(r"^[*_`]*(?:queries|query|gap|search|tìm kiếm|truy vấn|câu hỏi(?:\s+nghiên\s+cứu)?|khía cạnh|sub-question\s*\d*)[*_`]*:\s*", re.IGNORECASE),
    re.compile(r"^\d+[\.\)]\s*"),                            # "1. ", "2) "
    re.compile(r"^[-*•–—]\s*"),                               # "- ", "* ", "• "
    re.compile(r"^\[(?:query|gap|\d+)\]\s*", re.IGNORECASE),   # "[Query] ", "[1] "
    re.compile(r"^[\"']+|[\"']+$"),                          # leading or trailing quotes
]


def sanitize_aspect_query(raw_query: str) -> str:
    """Sanitize and strip forbidden metadata prefixes, formatting markers, and numbering.

    Ensures the returned query is purely technical and contains zero meta tokens.
    """
    if not raw_query:
        return ""

    cleaned = raw_query.strip()

    # Iteratively peel off prefixes (e.g. "1. QUERIES: - DeepSeek-R1")
    changed = True
    while changed:
        before = cleaned
        # Strip enclosing markdown artifacts at start or end before pattern check
        cleaned = re.sub(r"^[`*_]+|[`*_]+$", "", cleaned).strip()
        for pattern in FORBIDDEN_META_PATTERNS:
            cleaned = pattern.sub("", cleaned).strip()
        changed = (cleaned != before)

    # Collapse multiple whitespaces
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Strip trailing punctuation that shouldn't be in search queries
    cleaned = re.sub(r"[:;,.]+$", "", cleaned).strip()
    return cleaned



def generate_synthetic_error(error_type: str, message: str) -> str:
    """Generate a Hermes-compatible XML <tool_response> for zero-cost local self-correction."""
    payload = {
        "status": "error",
        "error_type": error_type,
        "message": message,
        "guidance": "Please adjust your reasoning and call delegate_research_queries or conclude_research with valid parameters.",
    }
    return f"<tool_response>\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n</tool_response>"


def _parse_tool_call_json(raw_json: str) -> dict[str, Any] | None:
    """Safely parse JSON from tool call string, attempting minor repairs if needed."""
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        # Try extracting JSON object substring
        match = re.search(r"\{.*\}", raw_json, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return None


def validate_and_repair_decision(raw_output: str, default_anchor: str = "") -> SupervisorDecision:
    """Defensively parse Supervisor output into a typed SupervisorDecision.

    Order of resolution:
    1. Hermes XML Envelope: <thought> and <tool_call>.
    2. Naked JSON (or markdown ```json ... ``` block).
    3. Plain text fallback: detects 'SUFFICIENT' or extracts queries via heuristic linting.

    Guarantees:
    - Never throws an exception.
    - Never produces a query containing 'QUERIES:', 'GAP:', or list numbers.
    - If no queries can be extracted and not sufficient, defaults to a single query using default_anchor.
    """
    if not raw_output or not raw_output.strip():
        return SupervisorDecision(
            thought="Empty model output.",
            status="researching",
            queries=[ResearchQueryAction(subject_anchor=default_anchor, technical_aspect="overview facts")] if default_anchor else [],
            gap_analysis="No output received from supervisor model.",
        )

    # 1. Check for Hermes XML Envelopes
    blocks = extract_hermes_blocks(raw_output)
    thought = blocks["thought"]
    tool_call_text = blocks["tool_call"]

    if tool_call_text:
        call_obj = _parse_tool_call_json(tool_call_text)
        if isinstance(call_obj, dict):
            # Format A: {"name": "conclude_research", "arguments": {...}}
            name = call_obj.get("name")
            args = call_obj.get("arguments", call_obj)
            if not isinstance(args, dict):
                args = {}

            if name == "conclude_research" or "completion_rationale" in args:
                return SupervisorDecision(
                    thought=thought,
                    status="completed",
                    synthesis_notes=args.get("completion_rationale", ""),
                    gap_analysis="",
                )

            if name == "delegate_research_queries" or "queries" in args:
                gap = args.get("gap_analysis", "")
                raw_queries = args.get("queries", [])
                actions: list[ResearchQueryAction] = []
                for q in raw_queries:
                    if isinstance(q, dict):
                        anchor = sanitize_aspect_query(q.get("subject_anchor", default_anchor))
                        aspect = sanitize_aspect_query(q.get("technical_aspect", ""))
                        tier = q.get("target_tier", "tier_a")
                        if aspect:
                            actions.append(ResearchQueryAction(
                                subject_anchor=anchor or default_anchor,
                                technical_aspect=aspect,
                                target_tier=tier if tier in ("tier_a", "tier_b") else "tier_a",
                            ))
                    elif isinstance(q, str):
                        clean_q = sanitize_aspect_query(q)
                        if clean_q:
                            actions.append(ResearchQueryAction(
                                subject_anchor=default_anchor,
                                technical_aspect=clean_q,
                                target_tier="tier_a",
                            ))
                if actions:
                    return SupervisorDecision(
                        thought=thought,
                        status="researching",
                        queries=actions,
                        gap_analysis=gap,
                    )

    # 2. Check for naked JSON or markdown ```json ... ``` block in raw_output
    json_candidate = None
    json_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_output, flags=re.DOTALL)
    if json_block_match:
        json_candidate = _parse_tool_call_json(json_block_match.group(1))
    elif raw_output.strip().startswith("{") and raw_output.strip().endswith("}"):
        json_candidate = _parse_tool_call_json(raw_output)

    if isinstance(json_candidate, dict):
        if "completion_rationale" in json_candidate or json_candidate.get("status") == "completed":
            return SupervisorDecision(
                thought=thought or json_candidate.get("thought", ""),
                status="completed",
                synthesis_notes=json_candidate.get("completion_rationale", ""),
            )
        if "queries" in json_candidate:
            actions = []
            for q in json_candidate.get("queries", []):
                if isinstance(q, dict):
                    anchor = sanitize_aspect_query(q.get("subject_anchor", default_anchor))
                    aspect = sanitize_aspect_query(q.get("technical_aspect", ""))
                    tier = q.get("target_tier", "tier_a")
                    if aspect:
                        actions.append(ResearchQueryAction(
                            subject_anchor=anchor or default_anchor,
                            technical_aspect=aspect,
                            target_tier=tier if tier in ("tier_a", "tier_b") else "tier_a",
                        ))
                elif isinstance(q, str):
                    clean_q = sanitize_aspect_query(q)
                    if clean_q:
                        actions.append(ResearchQueryAction(
                            subject_anchor=default_anchor,
                            technical_aspect=clean_q,
                        ))
            if actions:
                return SupervisorDecision(
                    thought=thought or json_candidate.get("thought", ""),
                    status="researching",
                    queries=actions,
                    gap_analysis=json_candidate.get("gap_analysis", ""),
                )

    # 3. Fallback Heuristic Text Parser
    clean_text = blocks.get("unwrapped_text", raw_output)

    # Check for completion token
    if "SUFFICIENT" in clean_text.upper() and not ("QUERIES:" in clean_text.upper() and "-" in clean_text):
        return SupervisorDecision(
            thought=thought,
            status="completed",
            synthesis_notes=clean_text.strip(),
        )

    # Extract GAP and QUERIES lines
    gap_desc = ""
    query_lines: list[str] = []

    # Look for explicit GAP: ... and QUERIES: ... markers
    if "GAP:" in clean_text:
        gap_match = re.search(r"GAP:\s*([^\n]+)", clean_text, flags=re.IGNORECASE)
        if gap_match:
            gap_desc = gap_match.group(1).strip()

    if "QUERIES:" in clean_text:
        parts = re.split(r"QUERIES:\s*", clean_text, maxsplit=1, flags=re.IGNORECASE)
        after_queries = parts[1] if len(parts) > 1 else ""
        for raw_line in after_queries.split("\n"):
            line = sanitize_aspect_query(raw_line)
            # Avoid empty or short garbage lines
            if line and len(line) >= 4 and not line.lower().startswith("gap"):
                query_lines.append(line)
    else:
        # Line-by-line fallback: scan for bullet points
        for raw_line in clean_text.split("\n"):
            stripped = raw_line.strip()
            if stripped.startswith(("-", "*", "1.", "2.", "3.", "•")):
                line = sanitize_aspect_query(stripped)
                if line and len(line) >= 6:
                    query_lines.append(line)

    actions = [
        ResearchQueryAction(
            subject_anchor=default_anchor,
            technical_aspect=q_text,
            target_tier="tier_a",
        )
        for q_text in query_lines[:4]
    ]

    # If still no queries could be parsed, check if it says sufficient or construct a fallback query
    if not actions:
        if "SUFFICIENT" in clean_text.upper():
            return SupervisorDecision(thought=thought, status="completed", synthesis_notes=clean_text)
        if default_anchor:
            actions = [ResearchQueryAction(subject_anchor=default_anchor, technical_aspect="key facts and evidence")]

    return SupervisorDecision(
        thought=thought,
        status="researching",
        queries=actions,
        gap_analysis=gap_desc or clean_text[:200],
    )
