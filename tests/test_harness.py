"""Comprehensive tests for Phase 18: Harness Guard Layer.

Tests:
1. Protocol & Hermes XML Envelopes
2. Pre-flight Linter & Sanitizer
3. Safe Decision Parser & Synthetic Error Reflection
4. Domain Authority Scorer & Tier Classification
5. Observation Density Filter & Content Chunker
6. Information Gain (ΔI) & Stagnation Detection
7. Supervisor & Researcher Node Integration
8. Clean Architecture Boundaries Audit
"""

import ast
import asyncio
from pathlib import Path

import pytest

from infra.harness import (
    FORBIDDEN_META_PATTERNS,
    ObservationSnippet,
    ResearchQueryAction,
    StagnationDetector,
    SupervisorDecision,
    TIER_A_DOMAINS,
    TIER_C_SPAM_SUBSTRINGS,
    calculate_information_gain,
    extract_hermes_blocks,
    filter_and_rank_snippets,
    format_hermes_tool_definition,
    generate_synthetic_error,
    is_spam_domain,
    sanitize_aspect_query,
    score_domain_authority,
    validate_and_repair_decision,
)
from infra.interfaces import LLMProvider, LLMResponse, SearchClient, SearchResult
from researcher.node import researcher_node
from state.schema import AgentState, ResearcherState
from supervisor.node import supervisor_node
from supervisor.stopping_rules import LoopBudget


# ---------------------------------------------------------------------------
# 1. Protocol & Hermes XML Envelopes
# ---------------------------------------------------------------------------

def test_research_query_action_to_search_query():
    action1 = ResearchQueryAction(
        subject_anchor="DeepSeek-R1",
        technical_aspect="Cold-start data multi-stage pipeline",
        target_tier="tier_a",
    )
    assert action1.to_search_query() == "DeepSeek-R1 Cold-start data multi-stage pipeline"

    # Avoid duplicate anchor if already in aspect
    action2 = ResearchQueryAction(
        subject_anchor="DeepSeek-R1",
        technical_aspect="deepseek-r1 architecture reinforcement learning",
    )
    assert action2.to_search_query() == "deepseek-r1 architecture reinforcement learning"

    # Empty anchor fallback
    action3 = ResearchQueryAction(subject_anchor="", technical_aspect="Qwen 2.5 benchmark")
    assert action3.to_search_query() == "Qwen 2.5 benchmark"


def test_format_hermes_tool_definition():
    tool_def = format_hermes_tool_definition()
    assert "<tools>" in tool_def
    assert "</tools>" in tool_def
    assert "delegate_research_queries" in tool_def
    assert "conclude_research" in tool_def


def test_extract_hermes_blocks():
    text = (
        "<thought>\nAnalyzing gap in empirical data for latency.\n</thought>\n"
        "<tool_call>\n"
        '{"name": "delegate_research_queries", "arguments": {"gap_analysis": "Missing latency", "queries": []}}\n'
        "</tool_call>\n"
        "Some outside text."
    )
    blocks = extract_hermes_blocks(text)
    assert "Analyzing gap in empirical data for latency." in blocks["thought"]
    assert "delegate_research_queries" in blocks["tool_call"]
    assert "Some outside text." in blocks["unwrapped_text"]


def test_extract_hermes_blocks_unclosed_defensive():
    unclosed = "<thought>Thinking without closing tag..."
    blocks = extract_hermes_blocks(unclosed)
    assert "Thinking without closing tag..." in blocks["thought"]


# ---------------------------------------------------------------------------
# 2. Pre-flight Linter & Sanitizer
# ---------------------------------------------------------------------------

def test_sanitize_aspect_query_removes_meta_patterns():
    # Test stripping of 'QUERIES:', numbers, list bullets, quotes
    dirty_inputs = [
        ("QUERIES: - DeepSeek-R1 latency benchmarks", "DeepSeek-R1 latency benchmarks"),
        ("4. QUERIES: Lãi suất mua nhà 2026", "Lãi suất mua nhà 2026"),
        ("GAP: 1) Cần bổ sung số liệu GDP vĩ mô:", "Cần bổ sung số liệu GDP vĩ mô"),
        ("- **Tìm kiếm:** So sánh hiệu năng RTX 4070 và RTX 4090", "So sánh hiệu năng RTX 4070 và RTX 4090"),
        ("Câu hỏi nghiên cứu: Quy chuẩn xây dựng chung cư;", "Quy chuẩn xây dựng chung cư"),
        ('"[Query] Tác động chính sách tiền tệ"', "Tác động chính sách tiền tệ"),
        ("Sub-question 2: Phân tích tỷ lệ thất nghiệp", "Phân tích tỷ lệ thất nghiệp"),
    ]
    for raw, expected in dirty_inputs:
        cleaned = sanitize_aspect_query(raw)
        assert cleaned == expected, f"Failed on raw: '{raw}' -> got '{cleaned}', expected '{expected}'"


def test_generate_synthetic_error():
    err_xml = generate_synthetic_error("SchemaValidationError", "Missing required field 'queries'")
    assert "<tool_response>" in err_xml
    assert "</tool_response>" in err_xml
    assert "SchemaValidationError" in err_xml
    assert "Missing required field 'queries'" in err_xml


# ---------------------------------------------------------------------------
# 3. Safe Decision Parser & Fallback Recovery
# ---------------------------------------------------------------------------

def test_validate_and_repair_with_hermes_tool_call():
    hermes_output = (
        "<thought>\nChecklist question 2 lacks quantitative evidence on batch latency.\n</thought>\n"
        "<tool_call>\n"
        "{\n"
        '  "name": "delegate_research_queries",\n'
        '  "arguments": {\n'
        '    "gap_analysis": "Missing throughput numbers under concurrency",\n'
        '    "queries": [\n'
        '      {"subject_anchor": "vLLM", "technical_aspect": "PagedAttention throughput benchmarks", "target_tier": "tier_a"}\n'
        "    ]\n"
        "  }\n"
        "}\n"
        "</tool_call>"
    )
    decision = validate_and_repair_decision(hermes_output, default_anchor="LLM Serving")
    assert decision.status == "researching"
    assert "Checklist question 2" in decision.thought
    assert len(decision.queries) == 1
    assert decision.queries[0].subject_anchor == "vLLM"
    assert decision.queries[0].technical_aspect == "PagedAttention throughput benchmarks"
    assert decision.queries[0].to_search_query() == "vLLM PagedAttention throughput benchmarks"


def test_validate_and_repair_with_conclude_research():
    hermes_conclude = (
        "<thought>All questions answered thoroughly.</thought>\n"
        "<tool_call>\n"
        '{"name": "conclude_research", "arguments": {"completion_rationale": "Sufficient evidence collected."}}\n'
        "</tool_call>"
    )
    decision = validate_and_repair_decision(hermes_conclude)
    assert decision.status == "completed"
    assert decision.is_completed is True
    assert decision.synthesis_notes == "Sufficient evidence collected."


def test_validate_and_repair_with_markdown_json():
    json_output = (
        "```json\n"
        "{\n"
        '  "gap_analysis": "Need specifics on mortgage rates",\n'
        '  "queries": [\n'
        '    {"subject_anchor": "Lãi suất", "technical_aspect": "cho vay mua nhà 2026"}\n'
        "  ]\n"
        "}\n"
        "```"
    )
    decision = validate_and_repair_decision(json_output)
    assert decision.status == "researching"
    assert len(decision.queries) == 1
    assert decision.queries[0].to_search_query() == "Lãi suất cho vay mua nhà 2026"


def test_validate_and_repair_with_plain_text_sufficient():
    text_output = "SUFFICIENT. All points in the research checklist are thoroughly supported by empirical data."
    decision = validate_and_repair_decision(text_output)
    assert decision.status == "completed"


def test_validate_and_repair_with_messy_plain_text_never_leaks_meta():
    messy_text = (
        "4. GAP: Chưa có thông tin về tác động tâm lý đối với Gen Z\n\n"
        "QUERIES:\n"
        "1. QUERIES: Khảo sát tâm lý mua nhà của thế hệ trẻ\n"
        "- 2. Hành vi tài chính cá nhân Gen Z khi lãi suất tăng cao\n"
        "- GAP: Không liên quan\n"
    )
    decision = validate_and_repair_decision(messy_text, default_anchor="Thị trường bất động sản")
    assert decision.status == "researching"
    assert len(decision.queries) >= 1
    for q in decision.queries:
        query_str = q.to_search_query()
        assert "QUERIES:" not in query_str
        assert "GAP:" not in query_str
        assert not query_str.startswith("1.")
        assert not query_str.startswith("-")


def test_validate_and_repair_empty_output_safe():
    decision = validate_and_repair_decision("", default_anchor="General Topic")
    assert decision.status == "researching"
    assert len(decision.queries) == 1
    assert "General Topic" in decision.queries[0].to_search_query()


# ---------------------------------------------------------------------------
# 4. Domain Authority Scorer & Tier Classification
# ---------------------------------------------------------------------------

def test_score_domain_authority_tiers():
    # Tier A (1.0)
    assert score_domain_authority("https://arxiv.org/abs/2401.12345") == 1.0
    assert score_domain_authority("https://github.com/huggingface/transformers") == 1.0
    assert score_domain_authority("https://openreview.net/forum?id=xyz") == 1.0
    assert score_domain_authority("https://cs.stanford.edu/research/paper.pdf") == 1.0

    # Tier B (0.7)
    assert score_domain_authority("https://vnexpress.net/kinh-te/bai-viet.html") == 0.7
    assert score_domain_authority("https://techcrunch.com/2026/01/ai-breakthrough") == 0.7
    assert score_domain_authority("https://investopedia.com/terms/m/mortgage.asp") == 0.7

    # Tier C (0.0 - dropped)
    assert score_domain_authority("https://www.merriam-webster.com/dictionary/intelligence") == 0.0
    assert score_domain_authority("https://dictionary.com/browse/research") == 0.0
    assert score_domain_authority("https://123docz.net/document/tai-lieu-on-tap.htm") == 0.0
    assert score_domain_authority("https://www.studocu.com/vn/document/bai-tap-kinh-te") == 0.0
    assert score_domain_authority("https://page1.vn/bai-viet-seo") == 0.0
    assert score_domain_authority("https://shopee.vn/product/12345") == 0.0
    assert score_domain_authority("https://youtube.com/watch?v=123") == 0.0
    assert score_domain_authority("https://tiktok.com/@user/video/123") == 0.0

    # Spam helper
    assert is_spam_domain("https://merriam-webster.com") is True
    assert is_spam_domain("https://arxiv.org") is False


# ---------------------------------------------------------------------------
# 5. Observation Density Filter & Content Chunker
# ---------------------------------------------------------------------------

def test_filter_and_rank_snippets_drops_spam_and_prioritizes_tier_a():
    mock_results = [
        SearchResult(
            url="https://www.merriam-webster.com/dictionary/neural",
            title="Definition of NEURAL",
            content="Neural adjective: of, relating to, or affecting a nerve or the nervous system.",
        ),
        SearchResult(
            url="https://studocu.com/vn/document/123",
            title="Báo cáo tiểu luận tài chính",
            content="Tài liệu ôn tập môn học đại cương trường đại học.",
        ),
        SearchResult(
            url="https://techblog.com/ml/deepseek-inference",
            title="DeepSeek-R1 Inference Analysis",
            content="We measure throughput and latency for DeepSeek-R1 reasoning models.",
        ),
        SearchResult(
            url="https://arxiv.org/abs/2501.12948",
            title="DeepSeek-R1: Incentivizing Reasoning Capability via Reinforcement Learning",
            content="This paper introduces DeepSeek-R1-Zero and DeepSeek-R1 trained via large-scale RL.",
        ),
    ]

    filtered = filter_and_rank_snippets(
        mock_results,
        query="DeepSeek-R1 reasoning reinforcement learning",
        max_snippets=3,
        max_chars_per_snippet=800,
    )

    # Must drop Merriam-Webster and Studocu (Tier C)
    urls = [s.url for s in filtered]
    assert "https://www.merriam-webster.com/dictionary/neural" not in urls
    assert "https://studocu.com/vn/document/123" not in urls

    # Arxiv (Tier A) should rank at the top
    assert len(filtered) == 2
    assert filtered[0].url == "https://arxiv.org/abs/2501.12948"
    assert filtered[0].domain_tier == "tier_a"
    assert filtered[0].authority_score == 1.0


def test_filter_and_rank_snippets_truncates_cleanly():
    long_content = (
        "First sentence explaining deep research foundations. "
        "Second sentence providing concrete latency numbers around 15ms. "
        "Third sentence analyzing scaling laws and architectural choices. "
        + ("Extremely long filler content that goes on and on. " * 30)
    )
    mock_results = [
        SearchResult(
            url="https://arxiv.org/abs/test",
            title="Research Paper",
            content=long_content,
        )
    ]
    filtered = filter_and_rank_snippets(mock_results, max_chars_per_snippet=200)
    assert len(filtered) == 1
    snippet = filtered[0]
    assert len(snippet.content) <= 205
    # Should end on a period or sentence boundary, not mid-word
    assert snippet.content.endswith((".", "..."))


# ---------------------------------------------------------------------------
# 6. Information Gain (ΔI) & Stagnation Detection
# ---------------------------------------------------------------------------

def test_calculate_information_gain():
    existing_notes = "Mô hình ngôn ngữ lớn huấn luyện bằng phương pháp supervised fine-tuning."
    new_informative = ["Kiến trúc Mixture of Experts MoE tối ưu hóa VRAM và tính toán song song."]
    gain_high = calculate_information_gain(existing_notes, new_informative)
    # High gain because MoE, VRAM, mixture, experts, parallel are new
    assert gain_high > 0.5

    redundant = ["Phương pháp supervised fine-tuning huấn luyện mô hình ngôn ngữ lớn."]
    gain_low = calculate_information_gain(existing_notes, redundant)
    # Very low gain because terms already exist in notebook
    assert gain_low < 0.2


def test_stagnation_detector():
    detector = StagnationDetector()

    # Round 1
    detector.record_round(["Tác động lãi suất vay mua nhà 2026", "Chính sách nhà ở xã hội"])
    assert detector.is_stagnated() is False

    # Round 2 with fresh queries
    detector.record_round(["Thống kê dư nợ tín dụng bất động sản", "Khảo sát thu nhập Gen Z"])
    assert detector.is_stagnated() is False

    # Round 3 repeating queries from Round 2
    detector.record_round(["Thống kê dư nợ tín dụng bất động sản", "Khảo sát thu nhập Gen Z"])
    assert detector.is_stagnated() is True


# ---------------------------------------------------------------------------
# 7. Supervisor & Researcher Node Integration with Harness
# ---------------------------------------------------------------------------

class MockLLM(LLMProvider):
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_prompt = ""

    async def complete(self, *, prompt: str, tools=None, max_tokens=None) -> LLMResponse:
        self.last_prompt = prompt
        return LLMResponse(content=self.response_text)


def test_supervisor_node_with_hermes_xml_integration():
    async def run():
        hermes_xml_reply = (
            "<thought>Need empirical evidence on inference speed on consumer GPUs.</thought>\n"
            "<tool_call>\n"
            "{\n"
            '  "name": "delegate_research_queries",\n'
            '  "arguments": {\n'
            '    "gap_analysis": "Missing benchmark for RTX 4070 12GB VRAM",\n'
            '    "queries": [\n'
            '      {"subject_anchor": "Qwen2.5-7B-Instruct", "technical_aspect": "RTX 4070 GGUF Q4_K_M tokens per second", "target_tier": "tier_a"}\n'
            "    ]\n"
            "  }\n"
            "}\n"
            "</tool_call>"
        )
        llm = MockLLM(hermes_xml_reply)
        state: AgentState = {
            "thread_id": "t1",
            "user_query": "Đo hiệu năng SLM trên RTX 4070",
            "clarification_history": [],
            "supervisor": {
                "brief": None,
                "compressed_notes": [],
                "current_round": 0,
                "researchers_spawned_total": 0,
                "status": "delegating",
            },
            "final_report": None,
        }

        update = await supervisor_node(state, llm=llm, budget=LoopBudget(max_rounds=3))
        sup = update["supervisor"]

        assert sup["status"] == "delegating"
        assert sup["current_round"] == 1
        assert "follow_up_queries" in sup
        assert len(sup["follow_up_queries"]) == 1
        query = sup["follow_up_queries"][0]
        assert "Qwen2.5-7B-Instruct RTX 4070 GGUF Q4_K_M" in query
        assert "QUERIES:" not in query
        assert "<thought>" in llm.last_prompt or "<tools>" in llm.last_prompt

    asyncio.run(run())


def test_researcher_node_drops_tier_c_and_condenses_observations():
    class MixedSearchClient(SearchClient):
        async def search(self, *, query: str, max_results: int = 5):
            return [
                SearchResult(
                    url="https://www.merriam-webster.com/dictionary/deep-learning",
                    title="Definition of Deep Learning",
                    content="A branch of machine learning based on artificial neural networks.",
                ),
                SearchResult(
                    url="https://arxiv.org/abs/2501.99999",
                    title="Deep Research with Local Small Language Models",
                    content="We show that 7B parameters SLMs quantized to 4-bit execute rigorous reasoning when guided by an ACI harness. " * 10,
                ),
            ]

    async def run():
        llm = MockLLM("Extracted findings on 7B parameter models ([https://arxiv.org/abs/2501.99999]).")
        researcher_state: ResearcherState = {
            "topic": "SLM Local Reasoning",
            "findings": [],
            "tool_calls_made": 0,
            "status": "in_progress",
        }

        update = await researcher_node(
            researcher_state,
            llm=llm,
            search_client=MixedSearchClient(),
        )

        assert update["status"] == "complete"
        assert len(update["visited_urls"]) == 1
        assert update["visited_urls"][0] == "https://arxiv.org/abs/2501.99999"
        # Merriam-Webster must be completely excluded from prompt and visited URLs
        assert "merriam-webster" not in llm.last_prompt
        assert "merriam-webster" not in update["visited_urls"]

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 8. Clean Architecture Boundaries Audit
# ---------------------------------------------------------------------------

def test_clean_architecture_boundaries_infra_harness():
    """Verify infra/harness/ does NOT import LangGraph, external SDKs, or network libraries."""
    harness_dir = Path(__file__).resolve().parent.parent / "src" / "infra" / "harness"
    forbidden_modules = {"langgraph", "groq", "litellm", "tavily", "fastapi", "requests", "urllib.request", "httpx"}

    py_files = list(harness_dir.glob("*.py"))
    assert len(py_files) > 0, "No harness python files found to test"
    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_pkg = alias.name.split(".")[0]
                    assert top_pkg not in forbidden_modules, (
                        f"Clean Architecture Violation: {py_file.name} imports forbidden '{alias.name}'"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top_pkg = node.module.split(".")[0]
                    assert top_pkg not in forbidden_modules, (
                        f"Clean Architecture Violation: {py_file.name} imports from forbidden '{node.module}'"
                    )
