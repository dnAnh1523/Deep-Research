"""Unit tests for Langfuse tracing integration (infra/tracing.py)."""

import os
from unittest.mock import MagicMock, patch
import pytest

from infra.tracing import (
    flush_tracing,
    get_langfuse_callback,
    is_langfuse_configured,
)


def test_is_langfuse_configured_false_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert not is_langfuse_configured()

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert not is_langfuse_configured()


def test_is_langfuse_configured_true_when_keys_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    assert is_langfuse_configured()


def test_get_langfuse_callback_returns_none_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert get_langfuse_callback() is None


def test_get_langfuse_callback_creates_handler_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-123")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-456")
    monkeypatch.setenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    # Mock CallbackHandler to avoid real network calls
    mock_handler_cls = MagicMock()
    with patch("langfuse.langchain.CallbackHandler", mock_handler_cls):
        handler = get_langfuse_callback()
        assert handler is not None
        mock_handler_cls.assert_called_once_with(
            public_key="pk-lf-123",
            secret_key="sk-lf-456",
            host="https://cloud.langfuse.com",
        )


def test_flush_tracing_safe_with_mock_and_none() -> None:
    # Safe with None
    flush_tracing(None)

    # Safe with mock handler
    mock_h = MagicMock()
    flush_tracing(mock_h)
    mock_h.flush.assert_called_once()
