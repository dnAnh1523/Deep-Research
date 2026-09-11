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


def test_get_checkpointer_defaults_to_in_memory_when_env_is_dev(monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    saver = get_checkpointer()
    assert isinstance(saver, InMemorySaver)

    monkeypatch.setenv("ENV", "local")
    saver_local = get_checkpointer()
    assert isinstance(saver_local, InMemorySaver)

    monkeypatch.setenv("ENV", "test")
    saver_test = get_checkpointer()
    assert isinstance(saver_test, InMemorySaver)


def test_get_postgres_checkpointer_raises_when_no_connection_string(monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="Connection string is required"):
        get_postgres_checkpointer()


def test_get_checkpointer_routes_to_postgres_when_env_is_prod(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # In prod, without connection string, should attempt postgres and raise ValueError
    with pytest.raises(ValueError, match="Connection string is required"):
        get_checkpointer()
