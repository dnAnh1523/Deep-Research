"""Semantic cache fingerprinting and key generation."""

import hashlib


def compute_fingerprint(*, prompt_template: str, code_version: str) -> str:
    """Compute a deterministic hash fingerprint from prompt template and code version.

    Ensures that any update to either prompt template or code version immediately
    invalidates stale cache entries.

    Returns:
        str: 16-character hexadecimal SHA-256 digest string.
    """
    payload = f"version:{code_version}|prompt:{prompt_template}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def build_cache_key(*, query_embedding_bucket: str, fingerprint: str) -> str:
    """Build a human-readable and inspectable semantic cache key.

    Contains both fingerprint and query embedding bucket for easy debugging.

    Returns:
        str: cache key formatted as 'cache:<fingerprint>:<query_embedding_bucket>'
    """
    return f"cache:{fingerprint}:{query_embedding_bucket}"
