"""Application composition root.

HTTP handlers should not know which provider, search vendor, or checkpointer is
active. This module assembles those implementations once at the application
boundary and injects the existing domain graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from graph import build_research_graph
from infra.checkpointer import get_checkpointer
from infra.llm.factory import build_model_routers
from infra.search_client import TavilySearchClient
from infra.settings import AppSettings
from supervisor.concurrency_gate import ConcurrencyGate


@dataclass(frozen=True)
class RuntimeComponents:
    llm: Any
    worker_llm: Any
    search_client: Any
    checkpointer: Any
    graph: Any


def build_runtime(settings: AppSettings | None = None) -> RuntimeComponents | None:
    """Build the graph when both an LLM and configured search client are available."""
    active_settings = settings or AppSettings.from_env()
    if active_settings.search_provider != "tavily" or not active_settings.tavily_api_key:
        return None

    llm, worker_llm = build_model_routers(active_settings)
    if llm is None:
        return None

    search_client = TavilySearchClient(api_key=active_settings.tavily_api_key)
    checkpointer = get_checkpointer()
    graph = build_research_graph(
        llm=llm,
        worker_llm=worker_llm,
        search_client=search_client,
        concurrency_gate=ConcurrencyGate(
            max_concurrent=active_settings.max_concurrent_researchers
        ),
        checkpointer=checkpointer,
    )
    return RuntimeComponents(
        llm=llm,
        worker_llm=worker_llm,
        search_client=search_client,
        checkpointer=checkpointer,
        graph=graph,
    )
