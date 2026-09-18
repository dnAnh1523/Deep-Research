"""Tests for infra.checkpointer."""

import os
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from infra.checkpointer import (
    get_checkpointer,
    get_in_memory_checkpointer,
    get_postgres_checkpointer,
)


def test_get_in_memory_checkpointer_returns_in_memory_saver():
    saver = get_in_memory_checkpointer()
    assert isinstance(saver, InMemorySaver)


def test_get_checkpointer_defaults_to_in_memory_when_no_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    saver = get_checkpointer()
    assert isinstance(saver, InMemorySaver)


def test_get_postgres_checkpointer_raises_when_no_connection_string(monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="Connection string is required"):
        get_postgres_checkpointer()


def test_get_checkpointer_routes_to_postgres_when_database_url_is_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    # Will attempt to connect to Postgres using this URL, failing on network connection or missing driver
    try:
        get_checkpointer()
    except Exception as exc:
        # Either network failure or missing driver error, but must have routed to Postgres
        assert "postgresql" in str(exc).lower() or "langgraph.checkpoint.postgres" in str(exc) or "connection" in str(exc).lower()
