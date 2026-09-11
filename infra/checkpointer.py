"""Checkpointer adapter managing session persistence.

Supports InMemorySaver for local development and testing (ENV=dev),
and PostgresSaver (pointing to Supabase/PostgreSQL) for production.
"""

import os
from typing import Any
from langgraph.checkpoint.memory import InMemorySaver


def get_in_memory_checkpointer() -> InMemorySaver:
    """Return an in-memory checkpointer suitable for development and fast testing."""
    return InMemorySaver()


def get_postgres_checkpointer(*, connection_string: str | None = None) -> Any:
    """Return a persistent Postgres checkpointer from environment or connection string.

    `PostgresSaver.from_conn_string()` is a context manager in current
    langgraph-checkpoint-postgres releases. The application needs a saver that
    stays alive for the process lifetime, so we own the psycopg connection here
    and initialize the checkpoint tables once.
    """
    conn_str = (
        connection_string
        or os.getenv("SUPABASE_DATABASE_URL")
        or os.getenv("DATABASE_URL")
    )
    if not conn_str:
        raise ValueError(
            "Connection string is required via parameter or SUPABASE_DATABASE_URL / DATABASE_URL environment variable."
        )

    try:
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore
        from psycopg import Connection
        from psycopg.rows import dict_row

        connection = Connection.connect(
            conn_str,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
        saver = PostgresSaver(connection)
        saver.setup()
        return saver
    except ImportError as exc:
        raise ImportError(
            "langgraph.checkpoint.postgres is not installed. "
            "Please install the 'production' extra or use InMemorySaver for development."
        ) from exc


def get_checkpointer() -> Any:
    """Retrieve checkpointer instance based on ENV environment variable.

    Returns InMemorySaver when ENV is 'dev', 'development', 'local', or 'test'.
    Returns PostgresSaver when ENV is 'prod' or 'production'.
    """
    env = os.getenv("ENV", "dev").strip().lower()
    if env in ("dev", "development", "local", "test"):
        return get_in_memory_checkpointer()
    return get_postgres_checkpointer()
