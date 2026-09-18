"""Graph Assembly for the Deep Research Agent.

Assembles the full multi-agent research pipeline using LangGraph:
SessionCheck -> Intent Arbitrator -> (Semantic Cache) -> Clarify -> Brief
             -> Supervisor ⇄ (Concurrency Gate -> Researcher Pool)
             -> Compress -> Dual-Layer Citation Verifier -> Reporting -> END

Rule: This file (along with */node.py) is the ONLY place allowed to import langgraph.
"""

import operator
from typing import Annotated, Any, Literal
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from clarify.node import clarify_node
from compression.node import compression_node
from infra.interfaces import LLMProvider, SearchClient
from reporting.node import reporting_node
from research_brief.node import research_brief_node
from research_brief.validation import ResearchBrief
from researcher.node import researcher_node
from state.schema import AgentState, ResearcherState
from supervisor.concurrency_gate import ConcurrencyGate
from supervisor.node import supervisor_node
from supervisor.stopping_rules import LoopBudget, should_force_stop
from verification.node import verification_node


class ResearchGraphState(AgentState):
    """Extended graph execution state with reducer for parallel fan-in."""

    raw_findings: Annotated[list[str], operator.add]
    visited_urls: Annotated[list[str], operator.add]
    sources: Annotated[list[dict], operator.add]
    intent: str
    cache_hit: bool


def build_research_graph(
    *,
    llm: LLMProvider,
    search_client: SearchClient,
    worker_llm: LLMProvider | None = None,
    concurrency_gate: ConcurrencyGate | None = None,
    checkpointer: Any = None,
    budget: LoopBudget | None = None,
    cache_store: dict[str, str] | None = None,
) -> CompiledStateGraph:
    """Build, wire, and compile the full Deep Research Agent StateGraph.

    Acceptance criteria:
    - Compile graph receives checkpointer as a parameter (injected from outside).
    - Routing for Intent Arbitrator and Semantic Cache uses add_conditional_edges.
    - Researcher fan-out uses Send with count exactly matching queries for the round.
    - Role-based routing: worker_llm powers researcher and compression;
      llm powers clarification, brief, supervision, verification, and reporting.
    """
    if concurrency_gate is None:
        concurrency_gate = ConcurrencyGate(max_concurrent=3)
    if budget is None:
        budget = LoopBudget()
    store = cache_store if cache_store is not None else {}
    w_llm = worker_llm if worker_llm is not None else llm

    # --- Node Callbacks ---

    async def session_check_step(state: ResearchGraphState) -> dict:
        thread_id = state.get("thread_id", "default_thread")
        query = state.get("user_query", "")
        sup = state.get("supervisor")
        if not sup:
            brief = ResearchBrief(
                objective=query, sub_questions=[], constraints=[]
            )
            sup = {
                "brief": brief,
                "compressed_notes": [],
                "current_round": 0,
                "researchers_spawned_total": 0,
                "status": "delegating",
            }
        return {
            "thread_id": thread_id,
            "user_query": query,
            "clarification_history": state.get("clarification_history", []),
            "supervisor": sup,
            "raw_findings": [],
            "visited_urls": state.get("visited_urls", []),
            "sources": state.get("sources", []),
            "final_report": state.get("final_report"),
            "intent": "RESEARCH",
            "cache_hit": False,
        }

    async def intent_arbitrator_step(state: ResearchGraphState) -> dict:
        query = state.get("user_query", "").strip().lower()
        if not query or any(
            w in query
            for w in [
                "chơi game",
                "kể chuyện cười",
                "hát đi",
                "thời tiết",
                "out of scope",
            ]
        ):
            intent = "OUT_OF_SCOPE"
        elif any(
            w in query
            for w in [
                "tóm tắt lại",
                "ngắn hơn",
                "lược bớt",
                "tổng hợp lại",
                "meta command",
            ]
        ):
            intent = "META_COMMAND"
        else:
            intent = "RESEARCH"
        return {"intent": intent}

    def route_intent(
        state: ResearchGraphState,
    ) -> Literal["out_of_scope", "meta_command", "semantic_cache"]:
        intent = state.get("intent", "RESEARCH")
        if intent == "OUT_OF_SCOPE":
            return "out_of_scope"
        elif intent == "META_COMMAND":
            return "meta_command"
        return "semantic_cache"

    async def out_of_scope_step(state: ResearchGraphState) -> dict:
        return {
            "final_report": "Yêu cầu nằm ngoài phạm vi nghiên cứu (OUT_OF_SCOPE)."
        }

    async def meta_command_step(state: ResearchGraphState) -> dict:
        sup = state.get("supervisor", {})
        notes = sup.get("compressed_notes", [])
        if notes:
            report = "# Tóm tắt báo cáo trước\n\n" + "\n".join(
                f"- {n}" for n in notes
            )
        else:
            report = "Không tìm thấy nội dung báo cáo cũ trong checkpoint để tóm tắt."
        return {"final_report": report}

    async def semantic_cache_step(state: ResearchGraphState) -> dict:
        query = state.get("user_query", "").strip().lower()
        if query in store:
            return {
                "cache_hit": True,
                "final_report": store[query],
            }
        return {"cache_hit": False}

    def route_semantic_cache(
        state: ResearchGraphState,
    ) -> Literal["reporting", "clarify"]:
        if state.get("cache_hit", False):
            return "reporting"
        return "clarify"

    async def clarify_step(state: ResearchGraphState) -> dict:
        return await clarify_node(state, llm=llm)

    async def research_brief_step(state: ResearchGraphState) -> dict:
        return await research_brief_node(state, llm=llm)

    async def supervisor_step(state: ResearchGraphState) -> dict:
        return await supervisor_node(state, llm=llm, budget=budget)

    def route_supervisor(state: ResearchGraphState):
        sup = state.get("supervisor", {})
        status = sup.get("status", "delegating")
        current_round = sup.get("current_round", 1)
        brief = sup.get("brief")
        seen_urls = list(set(state.get("visited_urls", [])))

        if status == "delegating":
            if current_round <= 1:
                queries = getattr(brief, "sub_questions", []) if brief else []
            else:
                queries = sup.get("follow_up_queries") or (
                    getattr(brief, "sub_questions", []) if brief else []
                )

            if queries:
                return [
                    Send(
                        "researcher",
                        {
                            "topic": q,
                            "findings": [],
                            "tool_calls_made": 0,
                            "status": "in_progress",
                            "seen_urls": seen_urls,
                        },
                    )
                    for q in queries
                ]
        return "verification"

    async def researcher_step(state: dict) -> dict:
        researcher_state: ResearcherState = {
            "topic": state.get("topic", ""),
            "findings": state.get("findings", []),
            "tool_calls_made": state.get("tool_calls_made", 0),
            "status": state.get("status", "in_progress"),
        }
        seen_urls = state.get("seen_urls", [])
        res = await concurrency_gate.run(
            researcher_node(
                researcher_state,
                llm=w_llm,
                search_client=search_client,
                seen_urls=seen_urls,
            )
        )
        return {
            "raw_findings": res.get("findings", []),
            "visited_urls": res.get("visited_urls", []),
            "sources": res.get("sources", []),
        }

    async def compression_step(state: ResearchGraphState) -> dict:
        compressed_res = await compression_node(state, llm=w_llm)
        sup = compressed_res.get("supervisor", state.get("supervisor", {}))
        return {
            "supervisor": sup,
            "raw_findings": [],
        }

    def route_compression(
        state: ResearchGraphState,
    ) -> Literal["supervisor", "verification"]:
        sup = state.get("supervisor", {})
        current_round = sup.get("current_round", 0)
        total_spawned = sup.get("researchers_spawned_total", 0)
        stop, _ = should_force_stop(
            current_round=current_round,
            total_researchers_spawned=total_spawned,
            budget=budget,
        )
        if stop or sup.get("status") == "writing_report":
            return "verification"
        return "supervisor"

    async def verification_step(state: ResearchGraphState) -> dict:
        return await verification_node(state, llm=llm)

    async def reporting_step(state: ResearchGraphState) -> dict:
        if state.get("cache_hit", False):
            return {"final_report": state.get("final_report")}
        res = await reporting_node(state, llm=llm)
        query = state.get("user_query", "").strip().lower()
        if query and res.get("final_report"):
            store[query] = res["final_report"]
        return res

    # --- Builder Construction ---
    builder = StateGraph(ResearchGraphState)

    builder.add_node("session_check", session_check_step)
    builder.add_node("intent_arbitrator", intent_arbitrator_step)
    builder.add_node("out_of_scope", out_of_scope_step)
    builder.add_node("meta_command", meta_command_step)
    builder.add_node("semantic_cache", semantic_cache_step)
    builder.add_node("clarify", clarify_step)
    builder.add_node("research_brief", research_brief_step)
    builder.add_node("supervisor", supervisor_step)
    builder.add_node("researcher", researcher_step)
    builder.add_node("compression", compression_step)
    builder.add_node("verification", verification_step)
    builder.add_node("reporting", reporting_step)

    # Wiring Edges
    builder.add_edge(START, "session_check")
    builder.add_edge("session_check", "intent_arbitrator")

    # Intent Arbitrator conditional edge
    builder.add_conditional_edges(
        "intent_arbitrator",
        route_intent,
        {
            "out_of_scope": "out_of_scope",
            "meta_command": "meta_command",
            "semantic_cache": "semantic_cache",
        },
    )
    builder.add_edge("out_of_scope", END)
    builder.add_edge("meta_command", END)

    # Semantic Cache conditional edge
    builder.add_conditional_edges(
        "semantic_cache",
        route_semantic_cache,
        {
            "reporting": "reporting",
            "clarify": "clarify",
        },
    )

    builder.add_edge("clarify", "research_brief")
    builder.add_edge("research_brief", "supervisor")

    # Supervisor conditional edge (fan-out via Send or transition to verification)
    builder.add_conditional_edges(
        "supervisor",
        route_supervisor,
        ["researcher", "verification"],
    )

    builder.add_edge("researcher", "compression")

    # Compression conditional loop back to supervisor or proceed to verification
    builder.add_conditional_edges(
        "compression",
        route_compression,
        {
            "supervisor": "supervisor",
            "verification": "verification",
        },
    )

    builder.add_edge("verification", "reporting")
    builder.add_edge("reporting", END)

    # Injected checkpointer
    return builder.compile(checkpointer=checkpointer)
