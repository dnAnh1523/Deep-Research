"""Unit tests for Phase 15: Local SLM (Ollama GGUF) Integration & Hybrid Worker Routing."""

import asyncio
from graph import build_research_graph
from infra.interfaces import LLMResponse, SearchResult
from infra.model_router import (
    ModelRouter,
    ProviderConfig,
    calculate_pay_as_you_go_cost,
)
from supervisor.stopping_rules import LoopBudget


def test_local_ollama_zero_cost_calculation():
    """Verify that local Ollama models (Qwen2.5 GGUF Q4_K_M etc.) have exactly $0.00 Pay-As-You-Go cost."""
    # 7B GGUF Q4_K_M
    cost_7b_q4 = calculate_pay_as_you_go_cost("ollama", "qwen2.5:7b-instruct-q4_k_m", 10_000, 2_000)
    assert cost_7b_q4 == 0.0

    # 7B standard tag
    cost_7b = calculate_pay_as_you_go_cost("ollama", "qwen2.5:7b", 50_000, 10_000)
    assert cost_7b == 0.0

    # 3B standard tag
    cost_3b = calculate_pay_as_you_go_cost("ollama", "qwen2.5:3b", 100_000, 20_000)
    assert cost_3b == 0.0

    # Case insensitive
    cost_upper = calculate_pay_as_you_go_cost("OLLAMA", "Qwen2.5:7B-Instruct-Q4_K_M", 5_000, 1_000)
    assert cost_upper == 0.0


def test_local_ollama_injects_dummy_key_and_options():
    """Verify that local Ollama config automatically gets dummy API key and runtime options."""
    async def run():
        recorded_calls = []

        async def mock_caller(**kwargs):
            recorded_calls.append(kwargs)
            return LLMResponse(
                content="Mock local output",
                model=kwargs.get("model", ""),
                provider="ollama",
                usage={"prompt_tokens": 100, "completion_tokens": 50},
            )

        local_cfg = ProviderConfig(
            provider="ollama",
            model="qwen2.5:7b-instruct-q4_k_m",
            api_base="http://localhost:11434/v1",
            # api_key is deliberately omitted to simulate local execution without credentials
        )
        fallback_cfg = ProviderConfig(
            provider="groq",
            model="openai/gpt-oss-120b",
            api_key="fallback_key",
        )

        router = ModelRouter(
            providers=[local_cfg],
            fallback=fallback_cfg,
            client_caller=mock_caller,
        )

        resp = await router.complete(prompt="Trích xuất số liệu tuyển dụng AI")
        assert resp.content == "Mock local output"
        assert resp.cost_usd == 0.0
        assert len(recorded_calls) == 1

        call_args = recorded_calls[0]
        # Verify effective API key is injected as dummy "ollama"
        assert call_args["api_key"] == "ollama"
        assert call_args["provider"] == "ollama"
        assert "localhost:11434" in call_args["api_base"]

    asyncio.run(run())


def test_hybrid_graph_routing_worker_vs_brain():
    """Verify that build_research_graph routes worker_llm to researcher and compression, and brain_llm to supervisor and reporting."""
    async def run():
        brain_calls = []
        worker_calls = []

        class MockBrainLLM:
            def __init__(self):
                self.supervisor_calls = 0

            async def complete(self, *, prompt: str, tools=None, max_tokens=None) -> LLMResponse:
                brain_calls.append(prompt)
                p_lower = prompt.lower()
                if "research planning" in p_lower or "sub_questions" in p_lower:
                    content = '{"objective": "Test", "sub_questions": ["q1"], "constraints": []}'
                elif "research supervisor" in p_lower or "checklist" in p_lower:
                    self.supervisor_calls += 1
                    if self.supervisor_calls == 1:
                        content = "GAP: Need info on q1.\nQUERIES:\n- Subquery 1"
                    else:
                        content = "SUFFICIENT"
                elif "clarify" in p_lower or "helpful research assistant" in p_lower:
                    content = "Xác nhận yêu cầu nghiên cứu"
                else:
                    content = "# Final Report\n\nKey finding from worker ([https://test.com/a])"
                return LLMResponse(content=content, provider="groq", model="openai/gpt-oss-120b")

        class MockWorkerLLM:
            async def complete(self, *, prompt: str, tools=None, max_tokens=None) -> LLMResponse:
                worker_calls.append(prompt)
                return LLMResponse(
                    content="Key finding from worker ([https://test.com/a])",
                    provider="ollama",
                    model="qwen2.5:7b-instruct-q4_k_m",
                )

        class MockSearchClient:
            async def search(self, *, query: str, max_results: int = 5):
                return [
                    SearchResult(
                        title="AI Job 1",
                        url="https://test.com/a",
                        content="Lương khởi điểm 15 triệu VND.",
                    )
                ]

        brain_llm = MockBrainLLM()
        worker_llm = MockWorkerLLM()
        search_client = MockSearchClient()

        graph = build_research_graph(
            llm=brain_llm,
            worker_llm=worker_llm,
            search_client=search_client,
            budget=LoopBudget(max_rounds=2),
        )

        initial_state = {
            "user_query": "Tìm việc Fresher AI Engineer",
            "thread_id": "test_hybrid",
        }

        result = await graph.ainvoke(initial_state)

        # Verify that worker_llm was used by researcher and compression
        assert len(worker_calls) > 0
        assert any("investigative research worker" in call or "sub_topic" in call for call in worker_calls)

        # Verify that brain_llm was used by brief/supervisor/reporting
        assert len(brain_calls) > 0
        assert result.get("final_report") is not None

    asyncio.run(run())


def test_graph_backward_compatibility_worker_llm_none():
    """Verify that build_research_graph functions identically when worker_llm is omitted (None)."""
    async def run():
        llm_calls = []

        class SingleMockLLM:
            def __init__(self):
                self.supervisor_calls = 0

            async def complete(self, *, prompt: str, tools=None, max_tokens=None) -> LLMResponse:
                llm_calls.append(prompt)
                p_lower = prompt.lower()
                if "research planning" in p_lower or "sub_questions" in p_lower:
                    content = '{"objective": "Test", "sub_questions": ["q1"], "constraints": []}'
                elif "research supervisor" in p_lower or "checklist" in p_lower:
                    self.supervisor_calls += 1
                    if self.supervisor_calls == 1:
                        content = "GAP: Need info on q1.\nQUERIES:\n- Subquery 1"
                    else:
                        content = "SUFFICIENT"
                elif "investigative research worker" in p_lower:
                    content = "Worker finding ([https://test.com/b])"
                elif "clarify" in p_lower or "helpful research assistant" in p_lower:
                    content = "Xác nhận"
                else:
                    content = "# Single LLM Report\n\nContent ([https://test.com/b])"
                return LLMResponse(content=content, provider="groq", model="openai/gpt-oss-120b")

        class MockSearchClient:
            async def search(self, *, query: str, max_results: int = 5):
                return [
                    SearchResult(
                        title="Title",
                        url="https://test.com/b",
                        content="Snippet content",
                    )
                ]

        single_llm = SingleMockLLM()
        search_client = MockSearchClient()

        graph = build_research_graph(
            llm=single_llm,
            worker_llm=None,  # Default fallback to single llm
            search_client=search_client,
            budget=LoopBudget(max_rounds=2),
        )

        result = await graph.ainvoke({"user_query": "Test query"})
        assert result.get("final_report") is not None
        assert len(llm_calls) >= 3  # brief, researcher, supervisor, reporting all went to single_llm

    asyncio.run(run())
