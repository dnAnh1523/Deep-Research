"""FastAPI Application for the Deep Research Agent.

Exposes REST and SSE streaming endpoints wrapping the LangGraph pipeline.
Acceptance criteria:
- Every request must have a session_id (header/cookie/body); auto-generated if missing.
- thread_id passed to graph.ainvoke() / graph.astream() maps 1-1 directly to session_id.
- SSE stream endpoint closes and cancels tasks immediately upon client disconnect.
"""

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any, AsyncGenerator
from fastapi import Cookie, FastAPI, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from graph import build_research_graph
from infra.bootstrap import build_runtime
from infra.checkpointer import get_checkpointer
from infra.interfaces import LLMProvider, SearchClient
from infra.settings import AppSettings
from infra.tracing import flush_tracing, get_langfuse_callback
from supervisor.concurrency_gate import ConcurrencyGate

logger = logging.getLogger(__name__)


def create_fallback_title(query: str) -> str:
    """Create a compact report name only when the title model is unavailable."""
    normalized = " ".join(query.strip().split()).rstrip(".!?")
    semantic_prefix = re.split(r"\s+(?:và|,|:|;)\s+", normalized, maxsplit=1)[0].strip()
    if len(semantic_prefix.split()) >= 4 and len(semantic_prefix) < len(normalized):
        return semantic_prefix
    return " ".join(normalized.split()[:12]) or "Kế hoạch nghiên cứu"


class ResearchRequest(BaseModel):
    """Request payload for initiating or continuing research."""

    query: str = Field(..., description="Research question or task")
    session_id: str | None = Field(
        None, description="Optional session/thread identifier"
    )
    clarification_history: list[str] = Field(
        default_factory=list, description="Optional Q&A clarification history"
    )


class ResearchResponse(BaseModel):
    """Response payload containing generated report and session state."""

    session_id: str
    final_report: str | None = None
    citations: dict[str, Any] | None = None
    supervisor: dict | None = None


class PlanRequest(BaseModel):
    """Request to create or refine a research plan."""

    query: str
    clarification_history: list[str] = Field(default_factory=list)


class PlanResponse(BaseModel):
    """Structured research plan for user review."""

    title: str
    steps: list[str]
    time_estimate: str = "Sẵn sàng sau vài phút"
    full_explanation: str


def resolve_session_id(
    body_id: str | None,
    header_id: str | None,
    cookie_id: str | None,
) -> str:
    """Resolve session_id prioritizing body -> header -> cookie -> auto-generate UUID."""
    if body_id and body_id.strip():
        return body_id.strip()
    if header_id and header_id.strip():
        return header_id.strip()
    if cookie_id and cookie_id.strip():
        return cookie_id.strip()
    return str(uuid.uuid4())


def create_app(
    *,
    graph: Any = None,
    checkpointer: Any = None,
    llm: LLMProvider | None = None,
    search_client: SearchClient | None = None,
    concurrency_gate: ConcurrencyGate | None = None,
) -> FastAPI:
    """Create and configure the FastAPI research agent application."""
    app = FastAPI(
        title="Deep Research Agent API",
        description="Provider-agnostic autonomous LangGraph Deep Research Agent",
        version="0.1.0",
    )

    settings = AppSettings.from_env()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize graph if not injected
    compiled_graph = graph
    active_llm: LLMProvider | None = llm
    if compiled_graph is None and llm is not None and search_client is not None:
        chk = checkpointer or get_checkpointer()
        compiled_graph = build_research_graph(
            llm=llm,
            search_client=search_client,
            concurrency_gate=concurrency_gate,
            checkpointer=chk,
        )
    elif compiled_graph is None:
        # Compose the graph from the user's provider/search configuration. No
        # provider or model is hard-coded into the HTTP layer.
        try:
            runtime = build_runtime(settings)
            if runtime is not None:
                active_llm = runtime.llm
                compiled_graph = runtime.graph
            else:
                logger.info(
                    "Graph not auto-initialized: configure PROVIDER_CONFIG_FILE, "
                    "an LLM provider, and TAVILY_API_KEY."
                )
        except Exception as exc:
            logger.warning("Auto-initialization of graph skipped: %s", exc)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "deep-research-agent"}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        """Report whether the graph has been composed with runtime dependencies."""
        if compiled_graph is None:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "reason": "Configure an LLM provider and search provider.",
                },
            )
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "service": "deep-research-agent"},
        )

    @app.post("/research/plan", response_model=PlanResponse)
    async def create_research_plan(body: PlanRequest) -> PlanResponse:
        """Create or refine a research plan for user clarification and review."""
        history_context = ""
        if body.clarification_history:
            history_context = "\nLịch sử điều chỉnh trước đó:\n" + "\n".join(
                f"- {h}" for h in body.clarification_history
            )

        prompt = (
            "Bạn là một trợ lý nghiên cứu thông minh của hệ thống Deep Research. "
            "Người dùng muốn tìm hiểu về một chủ đề bất kỳ.\n"
            f"Chủ đề/Câu hỏi: {body.query}\n"
            f"{history_context}\n\n"
            "Hãy lập một kế hoạch nghiên cứu thiết thực, súc tích gồm 5 đến 7 bước và trả về ĐÚNG định dạng JSON sau (không thêm markdown ngoài block json):\n"
            "{\n"
            '  "title": "<Tên báo cáo ngắn gọn 4-9 từ, không chép nguyên câu hỏi và không dùng dấu ba chấm>",\n'
            '  "steps": [\n'
            '    "<Bước 1 cụ thể cần tìm hiểu trên internet>",\n'
            '    "<Bước 2 cụ thể cần xác định phạm vi hoặc bối cảnh>",\n'
            '    "<Bước 3 cụ thể cần khảo sát bằng nguồn tin cậy>",\n'
            '    "<Bước 4 cụ thể cần đối chiếu dữ liệu hoặc trường hợp thực tế>",\n'
            '    "<Bước 5 cụ thể cần phân tích rủi ro, xu hướng hoặc khoảng trống>",\n'
            '    "<Bước 6 cụ thể để tổng hợp kết luận>"\n'
            "  ],\n"
            '  "time_estimate": "Sẵn sàng sau vài phút",\n'
            '  "full_explanation": "<Tóm tắt 1-2 câu kế hoạch cho người dùng nếu họ muốn chỉnh sửa>"\n'
            "}"
        )

        if active_llm is not None:
            try:
                resp = await active_llm.complete(prompt=prompt)
                raw_text = resp.content.strip()
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()
                parsed = json.loads(raw_text)
                return PlanResponse(
                    title=parsed.get("title") or create_fallback_title(body.query),
                    steps=parsed.get(
                        "steps",
                        [
                            f"Tìm kiếm thông tin tổng quan về {body.query}",
                            "Khảo sát các nguồn tin tức và bài viết phân tích",
                            "Tổng hợp và đánh giá các điểm cốt lõi",
                        ],
                    ),
                    time_estimate=parsed.get("time_estimate", "Sẵn sàng sau vài phút"),
                    full_explanation=parsed.get(
                        "full_explanation", f"Kế hoạch tìm hiểu chi tiết về {body.query}."
                    ),
                )
            except Exception as e:
                logger.warning("Failed to generate LLM plan: %s", e)

        return PlanResponse(
            title=create_fallback_title(body.query),
            steps=[
                f"Tìm kiếm thông tin tổng quan và bối cảnh về {body.query}",
                f"Xác định phạm vi, các yếu tố chính và bối cảnh của {body.query}",
                "Khảo sát các trang web, bài phân tích và nguồn tin tức uy tín",
                "Đánh giá, đối chiếu các quan điểm, số liệu và trường hợp thực tế",
                "Phân tích xu hướng, rủi ro và những điểm còn thiếu bằng chứng",
                "Tổng hợp các phát hiện chính thành kết luận có thể kiểm chứng",
            ],
            time_estimate="Sẵn sàng sau vài phút",
            full_explanation=f"Kế hoạch tìm hiểu chi tiết về {body.query}.",
        )

    @app.get("/api/latest-report")
    async def get_latest_report() -> dict[str, Any]:
        """Fetch the latest research report and structured citations from disk."""
        report_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "latest_report.md",
        )
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                content = f.read()

            from reporting.citation_registry import parse_sources_from_research_notes
            registry = parse_sources_from_research_notes([content])
            return {
                "report": content,
                "citations": registry.to_citation_dict(),
                "status": "available",
            }
        return {"report": "", "citations": {}, "status": "not_found"}

    @app.post("/research", response_model=ResearchResponse)
    async def run_research(
        request_body: ResearchRequest,
        response: Response,
        x_session_id: str | None = Header(None, alias="X-Session-ID"),
        session_id: str | None = Cookie(None),
    ) -> ResearchResponse:
        session_key = resolve_session_id(
            request_body.session_id, x_session_id, session_id
        )
        response.headers["X-Session-ID"] = session_key
        response.set_cookie(key="session_id", value=session_key, httponly=True)

        if compiled_graph is None:
            return ResearchResponse(
                session_id=session_key,
                final_report="Graph not initialized.",
            )

        # 1-1 direct mapping: thread_id must equal session_id
        tracer = get_langfuse_callback()
        config: dict[str, Any] = {"configurable": {"thread_id": session_key}}
        if tracer is not None:
            config["callbacks"] = [tracer]

        input_state = {
            "user_query": request_body.query,
            "thread_id": session_key,
            "clarification_history": request_body.clarification_history,
        }

        try:
            result = await compiled_graph.ainvoke(input_state, config=config)
        finally:
            flush_tracing(tracer)

        sup_state = result.get("supervisor")
        if sup_state and hasattr(sup_state, "get"):
            # Ensure serializable
            brief = sup_state.get("brief")
            if brief and not isinstance(brief, dict):
                sup_state = dict(sup_state)
                sup_state["brief"] = (
                    brief.__dict__ if hasattr(brief, "__dict__") else str(brief)
                )

        return ResearchResponse(
            session_id=session_key,
            final_report=result.get("final_report"),
            citations=result.get("citations"),
            supervisor=sup_state if isinstance(sup_state, dict) else None,
        )

    @app.post("/research/stream")
    async def stream_research(
        request_body: ResearchRequest,
        request: Request,
        x_session_id: str | None = Header(None, alias="X-Session-ID"),
        session_id: str | None = Cookie(None),
    ) -> StreamingResponse:
        session_key = resolve_session_id(
            request_body.session_id, x_session_id, session_id
        )

        async def event_generator() -> AsyncGenerator[str, None]:
            if compiled_graph is None:
                yield f"data: {json.dumps({'error': 'Graph not initialized'})}\n\n"
                return

            tracer = get_langfuse_callback()
            config: dict[str, Any] = {"configurable": {"thread_id": session_key}}
            if tracer is not None:
                config["callbacks"] = [tracer]

            input_state = {
                "user_query": request_body.query,
                "thread_id": session_key,
                "clarification_history": request_body.clarification_history,
            }

            try:
                async for event in compiled_graph.astream(
                    input_state, config=config, stream_mode="updates"
                ):
                    # Check if client disconnected mid-stream
                    if await request.is_disconnected():
                        logger.info(
                            "Client disconnected from SSE stream (session: %s). Aborting.",
                            session_key,
                        )
                        break

                    yield f"data: {json.dumps(event, default=str)}\n\n"
            except asyncio.CancelledError:
                logger.info(
                    "SSE stream cancelled due to connection termination."
                )
                raise
            except Exception:
                logger.exception("Error during streaming research (session=%s)", session_key)
                # Do not leak provider URLs, request bodies, or API errors to a
                # public browser client. Detailed context stays in server logs.
                yield f"data: {json.dumps({'error': 'Research stream failed. Check backend logs.'})}\n\n"
            finally:
                flush_tracing(tracer)

        response = StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
        )
        response.headers["X-Session-ID"] = session_key
        response.set_cookie(key="session_id", value=session_key, httponly=True)
        return response

    return app


app = create_app()
