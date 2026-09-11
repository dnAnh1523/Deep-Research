# Kiến trúc — Deep Research Agent

> **Tài liệu này mô tả kiến trúc thực tế của hệ thống tính đến Phase 22.**
> Đọc khi PLANNING bất kỳ thay đổi nào chạm tới flow tổng thể, khi cần hiểu vì sao một thành phần tồn tại, hoặc khi onboarding người mới.

---

## Tổng quan

Deep Research Agent là một hệ thống nghiên cứu tự động chạy trên **LangGraph**, được thiết kế cho **người dùng phổ thông** muốn tìm hiểu sâu về bất kỳ chủ đề nào. Hệ thống tự động tìm kiếm, tổng hợp và viết báo cáo có trích dẫn nguồn. Runtime hiện hỗ trợ cấu hình provider/model tuỳ ý qua `config/providers.json`; các bảng bên dưới ghi lại baseline free-tier ban đầu của dự án, không phải giới hạn kiến trúc.

**Stack chính:**
- **Orchestration:** LangGraph (Python)
- **LLM:** Provider/model tuỳ ý qua `config/providers.json` hoặc environment
- **Local SLM:** Ollama hoặc bất kỳ OpenAI-compatible local gateway nào
- **Search:** Tavily (free tier)
- **API:** FastAPI + SSE streaming
- **Frontend:** Vite + React 19 + Tailwind CSS v4
- **Checkpointer:** PostgresSaver (Supabase) / InMemorySaver (dev)

---

## Pipeline — Sơ đồ flow thực tế

```mermaid
graph TD
    START([User Query]) --> SC[Session Check]
    SC --> IA[Intent Arbitrator]

    IA -->|OUT_OF_SCOPE| OOS[Out of Scope → END]
    IA -->|META_COMMAND| MC[Meta Command → END]
    IA -->|RESEARCH| CACHE[Semantic Cache]

    CACHE -->|cache hit| RPT[Reporting → END]
    CACHE -->|cache miss| CLR[Clarify]

    CLR --> BRIEF[Research Brief]
    BRIEF --> SUP[Supervisor]

    SUP -->|delegating| FAN["Fan-out via Send()"]
    FAN --> R1[Researcher 1]
    FAN --> R2[Researcher 2]
    FAN --> RN[Researcher N]

    R1 --> CMP[Compression]
    R2 --> CMP
    RN --> CMP

    CMP -->|"should_force_stop = false"| SUP
    CMP -->|"should_force_stop = true"| VER[Verification]

    SUP -->|writing_report| VER
    VER --> RPT

    subgraph "Concurrency Gate"
        R1
        R2
        RN
    end

    subgraph "Harness Guard Layer"
        direction TB
        HGL1["Hermes SETP Linter"]
        HGL2["Domain Authority Scorer"]
        HGL3["Observation Density Filter"]
        HGL4["Convergence ΔI Guard"]
    end
```

### Giải thích luồng

1. **Session Check**: Khôi phục state từ checkpoint nếu có, tránh chạy lại từ đầu.
2. **Intent Arbitrator**: Phân loại request (OUT_OF_SCOPE / META_COMMAND / RESEARCH) — ngăn câu hỏi meta đơn giản kích hoạt cả pipeline nghiên cứu tốn kém.
3. **Semantic Cache**: Cosine similarity trên câu hỏi. Bắt buộc có `version fingerprint` + `dev-bypass`.
4. **Clarify → Research Brief**: Làm rõ mục tiêu nghiên cứu → sinh brief có cấu trúc (`objective`, `sub_questions`, `constraints`).
5. **Supervisor ⇄ Researcher Pool**: Vòng lặp multi-round. Supervisor quyết định sub-topics, fan-out N researcher qua `Send()`, mỗi researcher chạy cô lập qua Concurrency Gate (max N=3). Sau mỗi round, Compression nén findings, kiểm tra `should_force_stop`.
6. **Verification**: Dual-Layer Citation Verifier — Layer 1: LLM entailment check. Layer 2: URL validity.
7. **Reporting**: Sinh báo cáo Markdown với trích dẫn dạng `[A]`, `[B]`, `[C]`.

---

## Cấu trúc thư mục

```
Deep Research/
├── api/                          # FastAPI application
│   ├── __init__.py
│   └── app.py                    # REST + SSE endpoints
│
├── clarify/                      # Node: làm rõ mục tiêu
│   ├── __init__.py
│   └── node.py
│
├── research_brief/               # Node + Domain logic: sinh brief có cấu trúc
│   ├── __init__.py
│   ├── node.py
│   └── validation.py             # ResearchBrief dataclass (pure Python, no LangGraph)
│
├── supervisor/                   # Node + Domain logic: điều phối vòng lặp
│   ├── __init__.py
│   ├── node.py
│   ├── stopping_rules.py         # should_force_stop() — pure Python, no LangGraph
│   └── concurrency_gate.py       # Semaphore giới hạn researcher đồng thời
│
├── researcher/                   # Node: cào và tổng hợp dữ liệu web
│   ├── __init__.py
│   └── node.py
│
├── compression/                  # Node: nén findings giữa các round
│   ├── __init__.py
│   └── node.py
│
├── verification/                 # Node + Domain logic: dedup + citation verify
│   ├── __init__.py
│   ├── node.py
│   └── dedup.py                  # Source dedup — pure Python
│
├── reporting/                    # Node: sinh báo cáo Markdown + citation registry
│   ├── __init__.py
│   ├── node.py
│   └── citation_registry.py      # Parse và quản lý trích dẫn
│
├── caching/                      # Domain logic: semantic cache fingerprint
│   ├── __init__.py
│   └── fingerprint.py            # Version fingerprint — pure Python
│
├── state/                        # State schemas (TypedDict)
│   ├── __init__.py
│   └── schema.py                 # AgentState, SupervisorState, ResearcherState
│
├── infra/                        # Infrastructure layer (Humble Objects)
│   ├── __init__.py
│   ├── interfaces.py             # typing.Protocol: LLMProvider, SearchClient
│   ├── model_router.py           # Cooldown, fallback, pricing, Ollama support
│   ├── search_client.py          # Tavily wrapper
│   ├── checkpointer.py           # PostgresSaver / InMemorySaver
│   ├── rate_limiter.py           # Token bucket rate limiter
│   ├── temporal.py               # Temporal grounding (năm hiện tại cho truy vấn)
│   ├── tracing.py                # Langfuse callback
│   ├── ollama_manager.py         # Zero-touch lifecycle cho Local SLM
│   └── harness/                  # Agent Harness Guard Layer
│       ├── __init__.py
│       ├── protocol.py           # Hermes SETP schema, data contracts
│       ├── linter.py             # Pre-flight linter + synthetic error reflection
│       ├── observation_filter.py # Domain scorer + density filter
│       └── convergence.py        # Information Gain ΔI + stagnation guard
│
├── graph.py                      # Graph assembly — NƠI DUY NHẤT wiring LangGraph
│
├── frontend/                     # Vite + React 19 + Tailwind CSS v4
│   └── src/
│       ├── App.tsx               # Root component: Sidebar + ChatFeed + ResearchCanvas
│       ├── main.tsx              # Entry point
│       ├── index.css             # Tailwind CSS v4 + theme tokens
│       ├── components/           # UI components (xem docs/frontend.md)
│       ├── hooks/                # useResearchApi.ts — SSE + REST
│       ├── types/                # TypeScript interfaces
│       └── public/               # Static assets
│
├── tests/                        # 21 test files, 140+ tests
├── docs/                         # Tài liệu hệ thống
├── run_demo.py                   # CLI runner (terminal demo)
├── run_fullstack.py              # Fullstack runner (API + Frontend)
├── .env                          # Environment variables (gitignored)
└── .gitignore
```

---

## 3 tầng State (ephemeral — khác Checkpointer là persistent)

| Tầng | Scope | File |
|---|---|---|
| `AgentState` | Toàn flow — từ user query đến final report | [`state/schema.py`](../state/schema.py) |
| `SupervisorState` | Điều phối — brief, notes, round counter | [`state/schema.py`](../state/schema.py) |
| `ResearcherState` | Cô lập theo từng researcher — KHÔNG chia sẻ | [`state/schema.py`](../state/schema.py) |

`ResearchGraphState` (trong [`graph.py`](../graph.py)) mở rộng `AgentState` thêm `raw_findings`, `visited_urls`, `intent`, `cache_hit` — sử dụng `operator.add` reducer cho fan-in song song.

---

## Ranh giới Clean Architecture

```
┌────────────────────────────────────────────────────┐
│  Domain Logic (pure Python, test không cần network) │
│  research_brief/validation.py                       │
│  supervisor/stopping_rules.py                       │
│  verification/dedup.py                              │
│  caching/fingerprint.py                             │
│  infra/harness/convergence.py, observation_filter   │
├────────────────────────────────────────────────────┤
│  Node Functions (*/node.py)                         │
│  - Được phép import LangGraph types                 │
│  - Gọi LLM/Search qua Protocol, KHÔNG trực tiếp    │
├────────────────────────────────────────────────────┤
│  Graph Assembly (graph.py)                          │
│  - NƠI DUY NHẤT wiring LangGraph StateGraph        │
├────────────────────────────────────────────────────┤
│  Infrastructure (infra/)                            │
│  - model_router.py, search_client.py, checkpointer  │
│  - Humble Objects: mỏng, ngu ngơ, I/O thật         │
│  - Thay thế được mà không đụng domain logic         │
└────────────────────────────────────────────────────┘
```

**Quy tắc bất biến:**
- Node KHÔNG import trực tiếp `groq`, `litellm`, `tavily` — chỉ qua `infra/interfaces.py`
- File ngoài `graph.py` và `*/node.py` KHÔNG import `langgraph`
- Domain logic KHÔNG gọi network trực tiếp

---

## Model Routing

The runtime does not require a specific provider or model. Configure one or
more primary entries and an optional fallback in `config/providers.json`.
Cloud, local, hosted Ollama, Anthropic-native, and OpenAI-compatible gateways
can be mixed as long as the selected models support the capabilities required
by the pipeline. The cooldown key is `(provider, model)`.

The optional local worker path can route researcher/compression work through
Ollama or another local OpenAI-compatible gateway; it is disabled unless
explicitly configured.

---

## Harness Guard Layer

Nằm giữa Node Functions và hạ tầng bên ngoài, tổng hợp từ Hermes SETP + DeepSeek Rule-Based Verifiers + SWE-agent ACI:

| Component | Chức năng |
|---|---|
| **Hermes SETP Linter** | Chuẩn hóa query, synthetic error reflection ($0 cost) |
| **Domain Authority Scorer** | Tier A/B/C — loại 100% spam (Tier C) |
| **Observation Density Filter** | BM25 top-3 đoạn giàu dữ liệu nhất cho Local SLM |
| **Convergence ΔI Guard** | Đo bão hòa tri thức, tự dừng khi ΔI < threshold |

Các guard của harness được triển khai trong thư mục [`infra/harness/`](../infra/harness/). Ghi chú thiết kế nội bộ không nằm trong bản phát hành public.

---

## Temporal Grounding

[`infra/temporal.py`](../infra/temporal.py) tự động gắn mốc thời sự (năm hiện tại) vào truy vấn chứa từ khóa thời sự ("mới nhất", "hiện nay", "gần đây"), ngăn model trả lời bằng dữ liệu cũ trong training data.

---

## Observability

- **Langfuse tracing** ([`infra/tracing.py`](../infra/tracing.py)): Bật từ đầu, không để tới lúc debug mới thêm.
- **Pay-as-you-go cost tracking**: Mỗi LLM call ghi `latency_seconds` + `cost_usd` từ pricing catalog trong Model Router.
- **XAI Glass-Box logging**: Log từng quyết định của Supervisor, Researcher, Harness cho phép audit hậu kiểm.
