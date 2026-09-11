"""Tests for Module 5: Node Functions."""

import asyncio
from clarify.node import clarify_node
from compression.node import compression_node
from infra.interfaces import LLMProvider, LLMResponse, SearchClient, SearchResult
from reporting.node import reporting_node
from research_brief.node import research_brief_node
from research_brief.validation import ResearchBrief
from researcher.node import researcher_node
from state.schema import AgentState, ResearcherState
from supervisor.node import supervisor_node
from supervisor.stopping_rules import LoopBudget
from verification.dedup import Source
from verification.node import verification_node


class MockCountingLLMProvider:
    """Mock LLMProvider that records calls and call count."""

    def __init__(self, response_text: str = "Mocked LLM completion") -> None:
        self.response_text = response_text
        self.call_count = 0
        self.last_prompt = ""

    async def complete(
        self, *, prompt: str, tools: list[dict] | None = None
    ) -> LLMResponse:
        self.call_count += 1
        self.last_prompt = prompt
        return LLMResponse(content=self.response_text)


class MockSearchClient:
    """Mock SearchClient."""

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or [
            SearchResult(
                url="https://arxiv.org/abs/1",
                title="Paper 1",
                content="Key finding 1",
            )
        ]
        self.call_count = 0

    async def search(
        self, *, query: str, max_results: int = 5
    ) -> list[SearchResult]:
        self.call_count += 1
        return self.results


def _create_initial_agent_state(query: str = "Quantum computing algorithms") -> AgentState:
    brief = ResearchBrief(objective=query, sub_questions=["SubQ 1"], constraints=[])
    return {
        "thread_id": "test_thread",
        "user_query": query,
        "clarification_history": [],
        "supervisor": {
            "brief": brief,
            "compressed_notes": ["Initial note"],
            "current_round": 0,
            "researchers_spawned_total": 0,
            "status": "delegating",
        },
        "final_report": None,
    }


def test_clarify_node_call_limit_and_state_update():
    async def run():
        llm = MockCountingLLMProvider("Can you clarify the specific algorithms?")
        state = _create_initial_agent_state("Quantum")

        update = await clarify_node(state, llm=llm)
        assert llm.call_count <= 1
        assert len(update["clarification_history"]) == 1
        assert "clarify" in update["clarification_history"][0]

    asyncio.run(run())


def test_research_brief_node_delegates_to_validate_brief_and_call_limit():
    async def run():
        json_resp = (
            '{"objective": "Study QEC", '
            '"sub_questions": ["What is surface code?", "How to measure syndromes?"], '
            '"constraints": ["Focus on superconducting qubits"]}'
        )
        llm = MockCountingLLMProvider(json_resp)
        state = _create_initial_agent_state("Quantum Error Correction")

        update = await research_brief_node(state, llm=llm)
        assert llm.call_count <= 1
        brief = update["supervisor"]["brief"]
        assert isinstance(brief, ResearchBrief)
        assert brief.objective == "Study QEC"
        assert len(brief.sub_questions) == 2

    asyncio.run(run())


def test_supervisor_node_stops_when_budget_exceeded():
    async def run():
        llm = MockCountingLLMProvider()
        state = _create_initial_agent_state()
        state["supervisor"]["current_round"] = 3  # budget limit is 3
        budget = LoopBudget(max_rounds=3, max_researchers_total=12)

        update = await supervisor_node(state, llm=llm, budget=budget)
        # MUST stop and transition to writing_report without making an LLM call
        assert update["supervisor"]["status"] == "writing_report"
        assert llm.call_count == 0

    asyncio.run(run())


def test_supervisor_node_delegates_when_under_budget():
    async def run():
        llm = MockCountingLLMProvider()
        state = _create_initial_agent_state()
        state["supervisor"]["current_round"] = 1
        budget = LoopBudget(max_rounds=3, max_researchers_total=12)

        update = await supervisor_node(state, llm=llm, budget=budget)
        assert update["supervisor"]["status"] == "delegating"
        assert update["supervisor"]["current_round"] == 2
        # At most 1 call
        assert llm.call_count <= 1

    asyncio.run(run())


def test_researcher_node_executes_search_and_synthesis():
    async def run():
        llm = MockCountingLLMProvider("Surface codes achieve a 1% fault-tolerant threshold.")
        search_client = MockSearchClient()
        researcher_state: ResearcherState = {
            "topic": "Surface codes threshold",
            "findings": [],
            "tool_calls_made": 0,
            "status": "in_progress",
        }

        update = await researcher_node(researcher_state, llm=llm, search_client=search_client)
        assert update["status"] == "complete"
        assert update["tool_calls_made"] == 1
        assert len(update["findings"]) >= 1
        assert "fault-tolerant" in update["findings"][0]

    asyncio.run(run())


def test_compression_node_call_limit_and_state_update():
    async def run():
        llm = MockCountingLLMProvider("- Compressed: High coherence times achieved.")
        state = _create_initial_agent_state()

        update = await compression_node(state, llm=llm)
        assert llm.call_count <= 1
        notes = update["supervisor"]["compressed_notes"]
        assert len(notes) >= 2
        assert "Compressed" in notes[-1]

    asyncio.run(run())


def test_verification_node_delegates_to_dedup_and_call_limit():
    async def run():
        llm = MockCountingLLMProvider("Entailment verified.")
        state = _create_initial_agent_state()
        sources = [
            Source(url="https://www.nature.com/art1", title="Quantum Tech"),
            Source(url="https://nature.com/art2", title="  quantum   tech  "),  # duplicate
            Source(url="https://science.org/art3", title="Quantum Tech"),  # independent domain
        ]

        update = await verification_node(state, llm=llm, sources=sources)
        assert llm.call_count <= 1
        meta = update["verification_metadata"]
        # Group 1 (nature.com), Group 2 (science.org) -> 2 independent sources
        assert meta["independent_sources_count"] == 2
        assert meta["duplicate_groups_count"] == 2
        assert meta["entailment_status"] == "Entailment verified."

    asyncio.run(run())


def test_reporting_node_call_limit_and_final_report():
    async def run():
        llm = MockCountingLLMProvider("# Final Deep Research Report\n\nContent here...")
        state = _create_initial_agent_state()

        update = await reporting_node(state, llm=llm)
        assert llm.call_count <= 1
        assert update["supervisor"]["status"] == "done"
        assert "Final Deep Research Report" in update["final_report"]

    asyncio.run(run())


def test_reporting_node_auto_continuation_when_truncated():
    class TruncatedLLMProvider:
        def __init__(self):
            self.call_count = 0

        async def complete(self, *, prompt: str, tools=None, max_tokens=None):
            self.call_count += 1
            if self.call_count == 1:
                long_text = "# Survey\n\n" + "Detailed analysis text. " * 50 + "\n- **"
                return LLMResponse(content=long_text, finish_reason="length")
            return LLMResponse(
                content="Final Key Insights.\n\n## Conclusion\n\nAll goals achieved.\n\n## References\n\n[1] Paper."
            )

    async def run():
        llm = TruncatedLLMProvider()
        state = _create_initial_agent_state()

        update = await reporting_node(state, llm=llm)
        assert llm.call_count == 2
        assert update["supervisor"]["status"] == "done"
        report = update["final_report"]
        assert "Detailed analysis text" in report
        assert "## Conclusion" in report
        assert "## References" in report
        assert not report.endswith("- **")

    asyncio.run(run())


def test_reporting_node_context_engineering_and_dynamic_outline():
    """Verify prompt has XML isolation and incorporates dynamic sub_questions without domain bias."""
    async def run():
        llm = MockCountingLLMProvider("# Báo cáo Kinh tế Vĩ mô\n\nNội dung phân tích...")
        brief = ResearchBrief(
            objective="Phân tích tác động của lãi suất",
            sub_questions=[
                "Chính sách tiền tệ ảnh hưởng thế nào đến tiêu dùng?",
                "Doanh nghiệp vừa và nhỏ phản ứng ra sao với lãi suất cao?",
            ],
            constraints=["Số liệu giai đoạn 2020-2025"],
        )
        state: AgentState = {
            "thread_id": "macro_econ_thread",
            "user_query": "Nghiên cứu tác động lãi suất tới kinh tế vĩ mô",
            "clarification_history": [],
            "supervisor": {
                "brief": brief,
                "compressed_notes": ["Ghi chú 1 về CPI", "Ghi chú 2 về tín dụng"],
                "current_round": 0,
                "researchers_spawned_total": 0,
                "status": "delegating",
            },
            "final_report": None,
        }

        update = await reporting_node(state, llm=llm)
        prompt = llm.last_prompt

        # XML tags present
        assert "<system_instructions>" in prompt
        assert "<user_query>" in prompt
        assert "<research_objective>" in prompt
        assert "<research_questions>" in prompt
        assert "<verified_findings>" in prompt
        assert "<report_structure_requirements>" in prompt

        # Dynamic sub questions mapped
        assert "Chính sách tiền tệ ảnh hưởng thế nào đến tiêu dùng?" in prompt
        assert "Doanh nghiệp vừa và nhỏ phản ứng ra sao với lãi suất cao?" in prompt

        # Zero tech/GPU bias
        assert "VRAM" not in prompt
        assert "GPU" not in prompt

        assert update["supervisor"]["status"] == "done"
        assert "Báo cáo Kinh tế Vĩ mô" in update["final_report"]

    asyncio.run(run())


def test_reporting_node_defensively_strips_thinking_tags():
    """Verify any leaked <think>...</think> tags are stripped from final_report."""
    async def run():
        leaked_output = (
            "<think>\nLet me outline the macro report.\nFirst I will analyze GDP.\n</think>\n"
            "# Báo cáo Toàn diện\n\n## 1. Executive Summary\nPhân tích kinh tế vĩ mô.\n\n## Conclusion\nKết luận."
        )
        llm = MockCountingLLMProvider(leaked_output)
        state = _create_initial_agent_state("Tâm lý học hành vi")

        update = await reporting_node(state, llm=llm)
        report = update["final_report"]

        assert "<think>" not in report
        assert "</think>" not in report
        assert "Let me outline the macro report" not in report
        assert "# Báo cáo Toàn diện" in report
        assert "Phân tích kinh tế vĩ mô" in report

    asyncio.run(run())


def test_supervisor_node_gap_analysis_and_follow_up_queries():
    """Verify supervisor extracts GAP analysis and follow_up_queries when notes are insufficient."""
    async def run():
        llm_output = (
            "GAP: Missing specific data on mortgage rates in 2024 and youth demographics.\n"
            "QUERIES:\n"
            "- Lãi suất cho vay mua nhà các ngân hàng thương mại 2024\n"
            "- Tỷ lệ người trẻ dưới 35 tuổi mua nhà trả góp\n"
        )
        llm = MockCountingLLMProvider(llm_output)
        state = _create_initial_agent_state()
        state["supervisor"]["current_round"] = 1
        budget = LoopBudget(max_rounds=3, max_researchers_total=12)

        update = await supervisor_node(state, llm=llm, budget=budget)
        sup = update["supervisor"]

        assert sup["status"] == "delegating"
        assert sup["current_round"] == 2
        assert "Missing specific data" in sup["research_guidance"]
        assert len(sup["follow_up_queries"]) == 2
        assert "Lãi suất cho vay mua nhà" in sup["follow_up_queries"][0]
        assert "Tỷ lệ người trẻ" in sup["follow_up_queries"][1]

    asyncio.run(run())


def test_researcher_node_filters_seen_urls():
    """Verify researcher filters out URLs that have already been seen."""
    async def run():
        class MultiUrlSearchClient:
            async def search(self, *, query: str, max_results: int = 5):
                from infra.interfaces import SearchResult
                return [
                    SearchResult(url="https://seen.com/paper1", title="Old 1", content="Old content 1"),
                    SearchResult(url="https://new.com/paper2", title="New 2", content="Fresh data 2"),
                    SearchResult(url="https://new.com/paper3", title="New 3", content="Fresh data 3"),
                ]

        llm = MockCountingLLMProvider("Extracted fresh data ([https://new.com/paper2]).")
        researcher_state = {
            "topic": "Mortgage rates",
            "findings": [],
            "tool_calls_made": 0,
            "status": "in_progress",
        }

        update = await researcher_node(
            researcher_state,
            llm=llm,
            search_client=MultiUrlSearchClient(),
            seen_urls=["https://seen.com/paper1"],
        )

        assert update["status"] == "complete"
        assert "visited_urls" in update
        # https://seen.com/paper1 should be excluded
        assert "https://seen.com/paper1" not in update["visited_urls"]
        assert "https://new.com/paper2" in update["visited_urls"]
        assert "https://new.com/paper3" in update["visited_urls"]

    asyncio.run(run())


def test_reporting_node_fallback_guarantees_non_empty_report():
    """Verify that reporting_node never returns an empty report even if LLM returns empty content."""
    async def run():
        llm = MockCountingLLMProvider("")  # Returns completely empty
        state = _create_initial_agent_state("Lãi suất mua nhà")
        state["supervisor"]["compressed_notes"] = [
            "Lãi suất ưu đãi dao động từ 6-8%/năm ([https://bank.vn]).",
            "Thu nhập người trẻ cần đạt tối thiểu 25 triệu/tháng để vay mua nhà ([https://stat.vn]).",
        ]

def test_research_brief_need_based_and_orthogonal():
    """Verify research_brief prompt uses functional meta-prompting without fixed numbers or domain examples."""
    async def run():
        mock_json = '{"objective": "Thời lượng pin iPhone vs Samsung", "sub_questions": ["So sánh thời lượng pin On-screen"], "constraints": []}'
        llm = MockCountingLLMProvider(mock_json)
        state = _create_initial_agent_state("So sánh pin iPhone 16 và S24")

        update = await research_brief_node(state, llm=llm)
        prompt = llm.last_prompt

        assert "Need-based & Minimal Sizing" in prompt
        assert "Orthogonality" in prompt
        assert "2 to 5" not in prompt  # No hardcoded number of questions
        assert update["supervisor"]["brief"].sub_questions == ["So sánh thời lượng pin On-screen"]

    asyncio.run(run())


def test_supervisor_checklist_stopping_rule():
    """Verify supervisor passes sub_questions checklist and stops when SUFFICIENT is returned."""
    async def run():
        llm = MockCountingLLMProvider("SUFFICIENT")
        state = _create_initial_agent_state("Chính sách lãi suất")
        brief = ResearchBrief(
            objective="Đánh giá mặt bằng lãi suất",
            sub_questions=["Lãi suất huy động hiện tại là bao nhiêu?", "Lãi suất cho vay mua nhà ra sao?"],
            constraints=[],
        )
        state["supervisor"]["brief"] = brief
        state["supervisor"]["compressed_notes"] = [
            "Lãi suất huy động 12 tháng ở mức 5-6%/năm.",
            "Lãi suất cho vay mua nhà thả nổi từ 10-12%/năm.",
        ]

        update = await supervisor_node(state, llm=llm)
        prompt = llm.last_prompt

        # Checklist is present with numbered questions
        assert "<research_checklist>" in prompt
        assert "1. Lãi suất huy động hiện tại là bao nhiêu?" in prompt
        assert "2. Lãi suất cho vay mua nhà ra sao?" in prompt

        # Concludes with writing_report when sufficient
        assert update["supervisor"]["status"] == "writing_report"

    asyncio.run(run())


def test_researcher_url_sanitizer_removes_junk_urls():
    """Verify URL sanitizer eliminates video streaming, social feeds, and empty tag/category aggregators."""
    from researcher.node import is_valid_research_url

    # Valid research URLs
    assert is_valid_research_url("https://vnexpress.net/thoi-su/kinh-te-2026.html") is True
    assert is_valid_research_url("https://nhandan.vn/bai-viet-nghien-cuu.html") is True
    assert is_valid_research_url("https://federalreserve.gov/pubs/working-paper.pdf") is True

    # Video streaming platforms
    assert is_valid_research_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is False
    assert is_valid_research_url("https://youtu.be/abc1234") is False
    assert is_valid_research_url("https://tiktok.com/@user/video/123") is False

    # Social feeds
    assert is_valid_research_url("https://facebook.com/posts/123") is False
    assert is_valid_research_url("https://x.com/expert/status/123") is False
    assert is_valid_research_url("https://twitter.com/analyst/status/456") is False

    # Tag and category aggregator endpoints
    assert is_valid_research_url("https://tapchicongthuong.vn/hashtag/lai-suat-cho-vay-515.htm") is False
    assert is_valid_research_url("https://news.com/tag/bat-dong-san") is False
    assert is_valid_research_url("https://site.vn/chu-de/nha-dat-2026") is False
    assert is_valid_research_url("https://forum.org/category/general-discussion/") is False


def test_reporting_appends_sorted_alphabetical_references():
    """Verify that reporting extracts only actually cited sources and sorts them alphabetically A-B-C."""
    from reporting.node import extract_sources_from_notes, append_alphabetical_references

    notes = [
        "Lãi suất vay mua nhà tăng cao ([VnExpress: Lãi suất](https://vnexpress.net/lai-suat))",
        "Chính sách hỗ trợ nhà ở xã hội ([Báo Nhân Dân: Nhà ở](https://nhandan.vn/nha-o))",
        "Dữ liệu khảo sát độc lập (https://batdongsan.com.vn/khao-sat)",
        "Tài liệu không được trích dẫn ([Unused Source](https://unused.com/paper))",
    ]

    sources = extract_sources_from_notes(notes)
    assert len(sources) == 4

    # Report only cites source [1] (VnExpress) and [2] (Báo Nhân Dân)
    report_text = (
        "# Báo cáo nghiên cứu bất động sản\n\n"
        "Lãi suất vay mua nhà đang ở mức cao kỷ lục theo số liệu ngân hàng [1]. "
        "Tuy nhiên chính sách nhà ở xã hội vẫn đang hỗ trợ người thu nhập thấp [2].\n"
    )

    final_report = append_alphabetical_references(report_text, sources)

    assert "## Tài liệu tham khảo" in final_report
    # Only the cited sources should be present
    assert "https://vnexpress.net/lai-suat" in final_report
    assert "https://nhandan.vn/nha-o" in final_report
    assert "https://unused.com/paper" not in final_report

    # Alphabetical order: "Báo Nhân Dân" must precede "VnExpress"
    pos_nhandan = final_report.index("Báo Nhân Dân")
    pos_vnexpress = final_report.index("VnExpress")
    assert pos_nhandan < pos_vnexpress


