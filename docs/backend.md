# Backend — Deep Research Agent

> Mô tả toàn bộ backend Python: modules, luồng dữ liệu, API endpoints, infrastructure, và cách chạy.

---

## Entry Points

| File | Mục đích | Lệnh |
|---|---|---|
| [`run_demo.py`](../run_demo.py) | CLI runner — chạy pipeline đầy đủ từ terminal, xuất báo cáo vào `REPORT_STORAGE_DIR` | `python run_demo.py` |
| [`run_fullstack.py`](../run_fullstack.py) | Fullstack runner — khởi động Backend (port 8000) + Frontend (port 3000) đồng thời | `python run_fullstack.py` |
| [`api/app.py`](../api/app.py) | FastAPI server — REST + SSE endpoints | `uvicorn api.app:app --port 8000` |

---

## Modules theo domain

### Pipeline Nodes (theo thứ tự thực thi)

Mỗi module chứa `node.py` (LangGraph node function) và có thể chứa domain logic thuần (pure Python, test không cần network).

| Module | Thư mục | Vai trò | Domain logic |
|---|---|---|---|
| **Clarify** | [`clarify/`](../clarify) | Làm rõ mục tiêu nghiên cứu từ câu hỏi người dùng | — |
| **Research Brief** | [`research_brief/`](../research_brief) | Sinh brief có cấu trúc (objective, sub_questions, constraints) | `validation.py` — `ResearchBrief` dataclass |
| **Supervisor** | [`supervisor/`](../supervisor) | Điều phối vòng lặp nghiên cứu multi-round, quyết định sub-topics | `stopping_rules.py` — `should_force_stop()`, `LoopBudget` |
| **Researcher** | [`researcher/`](../researcher) | Cào và tổng hợp dữ liệu web cho một sub-topic | — |
| **Compression** | [`compression/`](../compression) | Nén findings giữa các round để giảm token | — |
| **Verification** | [`verification/`](../verification) | Dual-Layer Citation Verifier + Source dedup | `dedup.py` — `Source`, `deduplicate_sources()` |
| **Reporting** | [`reporting/`](../reporting) | Sinh báo cáo Markdown hoàn chỉnh với trích dẫn | `citation_registry.py` — `CitationRegistry` |

### Support Modules

| Module | Thư mục | Vai trò |
|---|---|---|
| **State** | [`state/`](../state) | TypedDict schemas: `AgentState`, `SupervisorState`, `ResearcherState` |
| **Caching** | [`caching/`](../caching) | Semantic cache fingerprint (version hash + dev-bypass) |

### Infrastructure (Humble Objects)

Tất cả nằm trong [`infra/`](../infra). Mỗi file là một wrapper mỏng quanh I/O thật, đằng sau `typing.Protocol`.

| File | Chức năng |
|---|---|
| [`interfaces.py`](../infra/interfaces.py) | `LLMProvider`, `SearchClient` Protocol — ranh giới Dependency Inversion |
| [`model_router.py`](../infra/model_router.py) | Cooldown `(provider, model)`, optional fallback chain, OpenAI-compatible + Anthropic protocols |
| [`search_client.py`](../infra/search_client.py) | Tavily wrapper, bóc tách `published_date` |
| [`checkpointer.py`](../infra/checkpointer.py) | PostgresSaver (Supabase) / InMemorySaver (dev) |
| [`settings.py`](../infra/settings.py) | Typed environment/runtime configuration |
| [`bootstrap.py`](../infra/bootstrap.py) | Composition root: settings → adapters → graph |
| [`llm/factory.py`](../infra/llm/factory.py) | JSON/environment provider factory for arbitrary models and endpoints |
| [`rate_limiter.py`](../infra/rate_limiter.py) | Optional token bucket rate limiter cho endpoint có quota |
| [`temporal.py`](../infra/temporal.py) | Temporal context — gắn năm hiện tại vào truy vấn thời sự |
| [`tracing.py`](../infra/tracing.py) | Langfuse callback setup |
| [`ollama_manager.py`](../infra/ollama_manager.py) | Zero-touch lifecycle cho Ollama + Local SLM |

### Harness Guard Layer

Nằm trong [`infra/harness/`](../infra/harness):

| File | Chức năng |
|---|---|
| [`protocol.py`](../infra/harness/protocol.py) | Hermes SETP schema, `ResearchQueryAction`, `SupervisorDecision`, `ObservationSnippet` |
| [`linter.py`](../infra/harness/linter.py) | Pre-flight sanitizer + synthetic error reflection ($0 cost) |
| [`observation_filter.py`](../infra/harness/observation_filter.py) | Domain Authority Scorer (Tier A/B/C) + BM25 density filter |
| [`convergence.py`](../infra/harness/convergence.py) | Information Gain ΔI calculator + stagnation guard |

---

## Graph Assembly

[`graph.py`](../graph.py) là nơi **duy nhất** wiring toàn bộ LangGraph `StateGraph`. Nó:

1. Định nghĩa `ResearchGraphState` (mở rộng `AgentState` thêm `raw_findings`, `visited_urls`, `intent`, `cache_hit`)
2. Tạo callback wrapper cho mỗi node
3. Wire edges: `START → session_check → intent_arbitrator → (conditional) → ... → reporting → END`
4. Fan-out researcher qua `Send()` — số lượng = số sub-topic Supervisor quyết định
5. Inject `checkpointer` khi compile

**Runtime routing** được cấu hình tại đây:
- `llm` → supervisor, brief, reporting, verification
- `worker_llm` (tuỳ chọn) → researcher, compression khi người dùng bật local worker

---

## API Endpoints

| Method | Path | Mục đích |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/ready` | Readiness/configuration check |
| `POST` | `/research/plan` | Sinh kế hoạch nghiên cứu (PlanRequest → PlanResponse) |
| `POST` | `/research` | Chạy pipeline đầy đủ (ResearchRequest → ResearchResponse) |
| `POST` | `/research/stream` | SSE stream — events real-time từng node |
| `GET` | `/api/latest-report` | Lấy báo cáo gần nhất từ disk + parsed citations |

### Session Management

- Session ID: body `session_id` → header `X-Session-ID` → cookie → auto-generate UUID
- `thread_id` truyền vào graph **map 1-1 trực tiếp** với `session_id`

### SSE Stream Format

Mỗi event là JSON từ `graph.astream(stream_mode="updates")`:
```
data: {"intent_arbitrator": {...}}
data: {"supervisor": {...}}
data: {"researcher": {...}}
data: {"reporting": {"final_report": "...", "citations": {...}}}
```

---

## Environment Variables

Cấu hình qua `.env` (xem `.env.example`):

| Variable | Bắt buộc | Mô tả |
|---|---|---|
| `PROVIDER_CONFIG_FILE` | Có cho cấu hình tuỳ ý | JSON mô tả provider/model, base URL, protocol và tên biến key |
| `TAVILY_API_KEY` | Có cho research web | API key Tavily search |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / provider keys | Tuỳ cấu hình | Các key được tham chiếu server-side từ `.env` |
| `DATABASE_URL` | Có khi `ENV=prod` | PostgresSaver cho checkpointer |
| `LANGFUSE_*` | Không | Tracing credentials |

Không có provider/model bắt buộc trong code. OpenAI-compatible gateway, Ollama
local/cloud, vLLM và LM Studio dùng `protocol: "openai-compatible"`; Anthropic
dùng `protocol: "anthropic"`. Xem `config/providers.example.json`.

---

## Test Suite

21 test files trong [`tests/`](../tests), tổng **140+ tests**, chạy bằng:

```bash
uv run pytest -v
```

Tất cả test chạy **không cần network** — sử dụng mock/fake cho LLM và Search thay vì gọi thật (F.I.R.S.T principle).

| Test file | Module được test |
|---|---|
| `test_research_brief_validation.py` | `research_brief/validation.py` |
| `test_supervisor_stopping_rules.py` | `supervisor/stopping_rules.py` |
| `test_verification_dedup.py` | `verification/dedup.py` |
| `test_caching_fingerprint.py` | `caching/fingerprint.py` |
| `test_infra_interfaces.py` | `infra/interfaces.py` |
| `test_model_router.py` | `infra/model_router.py` |
| `test_search_client.py` | `infra/search_client.py` |
| `test_checkpointer.py` | `infra/checkpointer.py` |
| `test_rate_limiter.py` | `infra/rate_limiter.py` |
| `test_temporal.py` | `infra/temporal.py` |
| `test_tracing.py` | `infra/tracing.py` |
| `test_harness.py` | `infra/harness/*` |
| `test_ollama_manager.py` | `infra/ollama_manager.py` |
| `test_local_slm.py` | Local SLM integration |
| `test_nodes.py` | Tất cả node functions |
| `test_concurrency_gate.py` | `supervisor/concurrency_gate.py` |
| `test_graph_assembly.py` | `graph.py` |
| `test_api_layer.py` | `api/app.py` |
| `test_citation_registry.py` | `reporting/citation_registry.py` |
| `test_state_schema.py` | `state/schema.py` |
