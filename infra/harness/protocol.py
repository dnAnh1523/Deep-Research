"""Protocol and data contracts for the Harness Guard Layer (Hermes SETP & SWE-agent ACI).

Provides structured actions, decisions, observation snippets, and Hermes XML envelope
helpers to eradicate raw text/regex ambiguity and enforce schema boundaries.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResearchQueryAction:
    """Structured action for a research worker search query.

    Separates fixed subject anchor (entity) from specific technical aspect,
    guaranteeing search queries are well-formed and targeted.
    """
    subject_anchor: str
    technical_aspect: str
    target_tier: str = "tier_a"  # "tier_a" (academic/official) | "tier_b" (general high-authority)

    def to_search_query(self) -> str:
        """Assembles a clean search query string, preventing duplicate entity mentions and anchoring time."""
        aspect = self.technical_aspect.strip()
        anchor = self.subject_anchor.strip()
        if not anchor:
            raw = aspect
        elif not aspect:
            raw = anchor
        elif anchor.lower() in aspect.lower():
            raw = aspect
        else:
            raw = f"{anchor} {aspect}"

        from infra.temporal import anchor_query_with_temporal_context
        return anchor_query_with_temporal_context(raw)


@dataclass
class ObservationSnippet:
    """High-density observation extracted from web search results."""
    title: str
    url: str
    content: str
    domain_tier: str = "tier_b"  # "tier_a" | "tier_b" | "tier_c"
    authority_score: float = 0.7
    density_score: float = 1.0
    published_date: str | None = None


@dataclass
class SupervisorDecision:
    """Structured decision output from Supervisor node."""
    thought: str = ""
    status: str = "researching"  # "researching" | "completed"
    queries: list[ResearchQueryAction] = field(default_factory=list)
    gap_analysis: str = ""
    synthesis_notes: str = ""

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"


def format_hermes_tool_definition() -> str:
    """Generate Hermes-compatible XML tool definitions for Schema-Enforced Tool Protocol (SETP)."""
    tools = [
        {
            "name": "delegate_research_queries",
            "description": (
                "Delegate focused research queries to worker researchers when checklist questions "
                "lack sufficient empirical evidence."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gap_analysis": {
                        "type": "string",
                        "description": "Specific checklist item or factual gap that remains unanswered.",
                    },
                    "queries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subject_anchor": {
                                    "type": "string",
                                    "description": "Primary entity or subject anchor (e.g., 'DeepSeek-R1', 'Lãi suất vay mua nhà').",
                                },
                                "technical_aspect": {
                                    "type": "string",
                                    "description": "Specific technical dimension or unanswered factual question.",
                                },
                                "target_tier": {
                                    "type": "string",
                                    "enum": ["tier_a", "tier_b"],
                                    "description": "Preferred source authority tier.",
                                },
                            },
                            "required": ["subject_anchor", "technical_aspect"],
                        },
                        "description": "List of 1 to 3 targeted search query actions.",
                    },
                },
                "required": ["gap_analysis", "queries"],
            },
        },
        {
            "name": "conclude_research",
            "description": (
                "Conclude research phase when all checklist items are thoroughly substantiated "
                "with facts, numbers, and concrete sources."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "completion_rationale": {
                        "type": "string",
                        "description": "Explanation of how all research checklist questions have been satisfied.",
                    },
                },
                "required": ["completion_rationale"],
            },
        },
    ]
    tool_json = json.dumps(tools, ensure_ascii=False, indent=2)
    return f"<tools>\n{tool_json}\n</tools>"


def extract_hermes_blocks(text: str) -> dict[str, str]:
    """Safely extract XML boundary blocks: <thought>, <tool_call>, <tool_response>.

    Handles unclosed or partially-formed tags defensively.
    """
    result: dict[str, str] = {
        "thought": "",
        "tool_call": "",
        "tool_response": "",
        "unwrapped_text": text,
    }

    if not text:
        return result

    # Extract <thought> ... </thought>
    thought_match = re.search(r"<thought>(.*?)(?:</thought>|$)", text, flags=re.DOTALL)
    if thought_match:
        result["thought"] = thought_match.group(1).strip()

    # Extract <tool_call> ... </tool_call>
    tool_call_match = re.search(r"<tool_call>(.*?)(?:</tool_call>|$)", text, flags=re.DOTALL)
    if tool_call_match:
        result["tool_call"] = tool_call_match.group(1).strip()

    # Extract <tool_response> ... </tool_response>
    tool_resp_match = re.search(r"<tool_response>(.*?)(?:</tool_response>|$)", text, flags=re.DOTALL)
    if tool_resp_match:
        result["tool_response"] = tool_resp_match.group(1).strip()

    # Remove the XML blocks to obtain unwrapped text
    clean_unwrapped = re.sub(
        r"<(thought|tool_call|tool_response)>.*?(?:</\1>|$)",
        "",
        text,
        flags=re.DOTALL,
    )
    result["unwrapped_text"] = clean_unwrapped.strip()
    return result
