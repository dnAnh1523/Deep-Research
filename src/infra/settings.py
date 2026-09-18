"""Typed runtime configuration loaded from environment variables.

The application deliberately keeps secrets in the environment and keeps
provider/model selection in a user-owned JSON file. This makes the repository
safe to publish while retaining a small, testable configuration seam.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class AppSettings:
    """Non-secret application settings plus provider/search environment values."""

    environment: str = "dev"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )
    provider_config_file: str = "config/providers.json"
    search_provider: str = "tavily"
    tavily_api_key: str | None = None
    database_url: str | None = None
    max_concurrent_researchers: int = 3
    report_storage_dir: str = "data/reports"
    local_slm_enabled: bool = False
    local_slm_model: str | None = None
    local_slm_base_url: str = "http://127.0.0.1:11434/v1"

    @classmethod
    def from_env(cls, *, root_dir: str | Path | None = None) -> "AppSettings":
        """Load `.env` from the repository root without printing any secrets."""
        root = Path(root_dir) if root_dir else Path(__file__).resolve().parents[2]
        load_dotenv(dotenv_path=root / ".env", override=False)

        database_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DATABASE_URL")
        return cls(
            environment=os.getenv("ENV", "dev").strip().lower(),
            api_host=os.getenv("API_HOST", "127.0.0.1"),
            api_port=int(os.getenv("API_PORT", "8000")),
            cors_origins=tuple(
                _split_csv(
                    os.getenv("CORS_ORIGINS"),
                    ["http://localhost:3000", "http://127.0.0.1:3000"],
                )
            ),
            provider_config_file=os.getenv(
                "PROVIDER_CONFIG_FILE", "config/providers.json"
            ),
            search_provider=os.getenv("SEARCH_PROVIDER", "tavily").strip().lower(),
            tavily_api_key=os.getenv("TAVILY_API_KEY") or None,
            database_url=database_url or None,
            max_concurrent_researchers=int(
                os.getenv("MAX_CONCURRENT_RESEARCHERS", "3")
            ),
            report_storage_dir=os.getenv("REPORT_STORAGE_DIR", "data/reports"),
            local_slm_enabled=_as_bool(os.getenv("LOCAL_SLM_ENABLED")),
            local_slm_model=os.getenv("LOCAL_SLM_MODEL") or None,
            local_slm_base_url=os.getenv(
                "LOCAL_SLM_BASE_URL", "http://127.0.0.1:11434/v1"
            ),
        )

    def resolve_path(self, value: str) -> Path:
        """Resolve a config path relative to the repository root when needed."""
        path = Path(value)
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parents[2] / path
