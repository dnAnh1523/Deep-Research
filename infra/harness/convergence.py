"""Natural Convergence Verifiers and Stagnation Guard for the Harness Guard Layer.

Inspired by DeepSeek Reasoning & Evaluation Harness:
1. Information Gain (ΔI) calculation to detect semantic saturation.
2. Stagnation Detector to detect repetitive queries and prevent endless loops.
"""

from __future__ import annotations

import re


def _tokenize_text(text: str) -> set[str]:
    """Extract meaningful entity and content tokens (length >= 3)."""
    if not text:
        return set()
    tokens = re.findall(r"\b[a-zA-Z0-9à-ỹÀ-Ỹ_]{3,}\b", text.lower())
    # Exclude ultra-common stop words
    stop_words = {
        "the", "and", "for", "with", "this", "that", "from", "are", "was", "were",
        "cua", "cac", "nhung", "trong", "cho", "voi", "nay", "duoc", "khong",
    }
    return {t for t in tokens if t not in stop_words}


def calculate_information_gain(existing_notebook: str, new_snippets: list[str]) -> float:
    """Calculate the Information Gain (ΔI) of new snippets against the accumulated research notebook.

    Formula:
        ΔI = |Entities_new \\ Entities_existing| / max(1, |Entities_new|)

    Returns a float in [0.0, 1.0].
    Values < 0.15 signify semantic saturation (diminishing returns).
    """
    if not new_snippets:
        return 0.0

    existing_tokens = _tokenize_text(existing_notebook)

    new_tokens: set[str] = set()
    for snippet in new_snippets:
        new_tokens.update(_tokenize_text(snippet))

    if not new_tokens:
        return 0.0

    novel_tokens = new_tokens - existing_tokens
    gain = len(novel_tokens) / len(new_tokens)
    return round(gain, 4)


class StagnationDetector:
    """Tracks research queries across rounds to detect cyclical repetition and stagnation."""

    def __init__(self) -> None:
        self.history: list[list[str]] = []

    def record_round(self, queries: list[str]) -> None:
        """Record the list of queries issued in the current round."""
        clean_queries = [q.strip().lower() for q in queries if q and q.strip()]
        self.history.append(clean_queries)

    def is_stagnated(self, similarity_threshold: float = 0.8) -> bool:
        """Check if the latest round's queries are repetitive or stagnated compared to the previous round.

        Returns True if:
        - The latest round has queries identical or highly overlapping (Jaccard similarity >= threshold)
          with the immediately preceding round.
        - Two consecutive rounds generated the exact same query set.
        """
        if len(self.history) < 2:
            return False

        prev_round = self.history[-2]
        curr_round = self.history[-1]

        if not curr_round:
            # No queries issued in current round is stagnation unless completed
            return True

        # Check exact query set equality
        if set(prev_round) == set(curr_round):
            return True

        # Token-based Jaccard similarity across rounds
        prev_tokens: set[str] = set()
        for q in prev_round:
            prev_tokens.update(_tokenize_text(q))

        curr_tokens: set[str] = set()
        for q in curr_round:
            curr_tokens.update(_tokenize_text(q))

        if not prev_tokens or not curr_tokens:
            return False

        intersection = prev_tokens & curr_tokens
        union = prev_tokens | curr_tokens

        jaccard = len(intersection) / len(union) if union else 0.0
        return jaccard >= similarity_threshold
