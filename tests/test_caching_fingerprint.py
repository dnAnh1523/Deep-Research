"""Tests for caching.fingerprint."""

from caching.fingerprint import build_cache_key, compute_fingerprint


def test_fingerprint_deterministic():
    fp1 = compute_fingerprint(
        prompt_template="Bạn là trợ lý nghiên cứu khoa học...",
        code_version="v1.0.0",
    )
    fp2 = compute_fingerprint(
        prompt_template="Bạn là trợ lý nghiên cứu khoa học...",
        code_version="v1.0.0",
    )
    assert fp1 == fp2
    assert isinstance(fp1, str)
    assert len(fp1) > 0


def test_fingerprint_changes_when_code_version_changes_by_one_char():
    fp1 = compute_fingerprint(
        prompt_template="Same prompt template",
        code_version="v1.0.0",
    )
    fp2 = compute_fingerprint(
        prompt_template="Same prompt template",
        code_version="v1.0.1",
    )
    assert fp1 != fp2


def test_fingerprint_changes_when_prompt_template_changes_by_one_char():
    fp1 = compute_fingerprint(
        prompt_template="Same prompt template.",
        code_version="v1.0.0",
    )
    fp2 = compute_fingerprint(
        prompt_template="Same prompt template!",
        code_version="v1.0.0",
    )
    assert fp1 != fp2


def test_build_cache_key_contains_fingerprint_and_bucket():
    fp = compute_fingerprint(prompt_template="test", code_version="1.0")
    bucket = "cluster_42_emb"
    cache_key = build_cache_key(query_embedding_bucket=bucket, fingerprint=fp)

    assert fp in cache_key
    assert bucket in cache_key
    assert cache_key.startswith("cache:")
