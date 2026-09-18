"""Reporting node function.

Generates final comprehensive research report in Markdown.
Follows Context Engineering principles: XML isolation, functional descriptions (no hardcoded examples),
adaptive thematic outlining, and seamless continuation.
"""

import re
from typing import Any
from infra.interfaces import LLMProvider
from infra.temporal import get_temporal_context
from reporting.citation_registry import CitationRegistry, parse_sources_from_research_notes
from state.schema import AgentState


def _clean_report_text(text: str) -> str:
    """Clean and strip model reasoning tags defensively, preserving content if no outer text exists."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in cleaned:
        tail_stripped = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
        if tail_stripped.strip():
            cleaned = tail_stripped
        else:
            # If model produced its entire answer inside <think>, strip the tag itself rather than losing text
            cleaned = re.sub(r"</?think>", "", text).strip()
    cleaned = re.sub(r"</think>", "", cleaned)
    return cleaned.strip()


def extract_sources_from_notes(notes: list[str]) -> list[dict[str, str]]:
    """Extract unique valid sources (title, url) from research notes."""
    seen_urls: set[str] = set()
    sources: list[dict[str, str]] = []
    for note in notes:
        # Match markdown links: [Title](url)
        md_matches = re.findall(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", note)
        for title, url in md_matches:
            url_clean = url.rstrip(".,;)")
            if url_clean not in seen_urls:
                seen_urls.add(url_clean)
                sources.append({"title": title.strip(), "url": url_clean})

        # Match standalone URLs: (https://...) or https://...
        raw_urls = re.findall(r"(https?://[^\s\)\],]+)", note)
        for url in raw_urls:
            url_clean = url.rstrip(".,;)")
            if url_clean not in seen_urls:
                seen_urls.add(url_clean)
                from urllib.parse import urlparse
                parsed = urlparse(url_clean)
                domain = parsed.netloc.replace("www.", "")
                path_parts = [p for p in parsed.path.strip("/").split("/") if p]
                slug = path_parts[-1].replace("-", " ").replace("_", " ") if path_parts else ""
                title = f"{domain}: {slug[:45]}" if slug else domain
                sources.append({"title": title.strip(), "url": url_clean})
    return sources


def append_alphabetical_references(report_text: str, sources: list[dict[str, str]]) -> str:
    """Identify actually cited sources, sort alphabetically by title, and append References section."""
    if not sources or not report_text.strip():
        return report_text

    # Detect which sources were actually cited in the report
    cited_indices: set[int] = set()
    cited_urls: set[str] = set()

    # 1. Look for numeric bracket citations: [1], [2], 【1】, 【2】
    num_citations = re.findall(r"(?:\[|【)(\d{1,3})(?:\]|】)", report_text)
    for num_str in num_citations:
        idx = int(num_str) - 1  # 1-based indexing
        if 0 <= idx < len(sources):
            cited_indices.add(idx)

    # 2. Look for direct URL citations in report
    for s in sources:
        if s["url"] in report_text:
            cited_urls.add(s["url"])

    # Collect actually cited sources
    cited_sources: list[dict[str, str]] = []
    for i, s in enumerate(sources):
        if i in cited_indices or s["url"] in cited_urls:
            cited_sources.append(s)

    # Fallback: if model did not use numbered citations or URLs, include top available sources
    if not cited_sources:
        cited_sources = sources[:10]

    # Deduplicate by URL
    unique_cited: list[dict[str, str]] = []
    seen: set[str] = set()
    for s in cited_sources:
        if s["url"] not in seen:
            seen.add(s["url"])
            unique_cited.append(s)

    # Sort alphabetically by title
    sorted_sources = sorted(unique_cited, key=lambda s: s["title"].lower())

    # Detect language for section header
    is_vietnamese = any(
        w in report_text.lower()
        for w in ["báo cáo", "nghiên cứu", "kết luận", "thị trường", "lãi suất", "tổng quan", "phân tích"]
    )
    header = "## Tài liệu tham khảo" if is_vietnamese else "## References"

    # Remove any existing incomplete or placeholder references section
    cleaned_report = re.sub(
        rf"(?i)\n*#+\s*(?:references|tài liệu tham khảo|tài liệu nguồn)\s*.*",
        "",
        report_text,
        flags=re.DOTALL,
    ).rstrip()

    ref_lines = [f"\n\n---\n\n{header}\n"]
    for i, s in enumerate(sorted_sources, 1):
        ref_lines.append(f"{i}. [{s['title']}]({s['url']})")

    return cleaned_report + "\n" + "\n".join(ref_lines)


def _build_reporting_prompt(
    user_query: str,
    brief: Any | None,
    notes: list[str],
    registry: CitationRegistry,
) -> str:
    """Build a general-purpose, description-driven research synthesis prompt with XML isolation."""
    objective = getattr(brief, "objective", user_query) or user_query
    sub_questions = getattr(brief, "sub_questions", []) or []

    if sub_questions:
        sub_q_text = "\n".join(f"- {q}" for q in sub_questions)
    else:
        sub_q_text = "- Address the central query with multifaceted, in-depth analysis."

    formatted_notes = "\n".join(f"- {note}" for note in notes) if notes else "No notes collected."
    sources_text = registry.format_sources_prompt() or "No explicit external sources available."

    temporal_xml = get_temporal_context().format_temporal_anchor_xml()

    return f"""<system_instructions>
You are an expert deep research assistant.
Your goal is to synthesize the verified findings below into a clear, comprehensive, and well-structured research report in Markdown.
Respond in the primary language used in the user query.

{temporal_xml}

Guidelines:
1. Direct & Substantive: Address the user's request and research questions thoroughly. Provide concrete insights, facts, and explanations rather than vague generalizations.
2. Chronological Precedence & Explicit Dating:
   - Ground all time-sensitive data, metrics, policies, and developments with explicit years or dates (e.g., 'tính đến quý 3/2026', 'trong năm 2026'). Avoid naked relative terms like 'hiện nay' or 'gần đây' without temporal anchors.
   - Newer verified sources supersede older historical forecasts. If past projections conflict with contemporary evidence, report the current factual status and clearly distinguish between historical context and contemporary state.
3. Natural, Practical Tone: Match the tone and depth to the topic (e.g., practical and structured for comparisons or guides; precise and analytical for technical or economic questions). Use tables or lists when helpful for clarity.
4. Evidence Attribution & Multi-Source Synthesis:
   - Ground all assertions, figures, and claims using bracketed numbers [1], [2], etc., matching the available sources.
   - MULTI-SOURCE SYNTHESIS: If an assertion or paragraph synthesizes facts, findings, or viewpoints from MULTIPLE sources (e.g., source A, source B, and source C), you MUST cite ALL contributing sources together (e.g., [1][2][3] or [1, 2, 3]). Never omit contributing sources.
   - CANONICAL NUMBERING: Each document has a unique number. Use that exact assigned number consistently whenever citing that document anywhere in the report.
5. Completeness: Produce a fully finished report without cutting off prematurely.
</system_instructions>

<user_query>
{user_query}
</user_query>

<research_objective>
{objective}
</research_objective>

<research_questions>
{sub_q_text}
</research_questions>

<available_sources>
{sources_text}
</available_sources>

<verified_findings>
{formatted_notes}
</verified_findings>

<report_structure_requirements>
- If the user explicitly requested a specific structure (such as IMRaD, SWOT, or a designated section list), follow that structure strictly.
- Otherwise, organize the report naturally:
  1. Summary & Key Takeaways: Concise overview of core conclusions.
  2. In-Depth Analysis: Clear sections addressing each research question.
  3. Practical Insights / Trade-offs: Real-world implications, comparisons, or considerations when appropriate.
</report_structure_requirements>"""



async def reporting_node(
    state: AgentState,
    *,
    llm: LLMProvider | None = None,
) -> dict:
    """Synthesize verified notes into the final markdown report.

    At most 1 call to LLMProvider.complete() (plus optional seamless continuation if truncated).
    Updates final_report and sets supervisor['status'] = 'done'.
    """
    sup_state = dict(state.get("supervisor", {}))
    brief = sup_state.get("brief")
    notes = sup_state.get("compressed_notes", [])
    user_query = state.get("user_query", "")

    registry = parse_sources_from_research_notes(notes)
    sources = [{"title": d.title, "url": d.url} for d in registry.get_all_ordered()]
    final_report = ""

    if llm is not None:
        prompt = _build_reporting_prompt(user_query, brief, notes, registry)
        try:
            response = await llm.complete(prompt=prompt, max_tokens=4096)
        except TypeError:
            response = await llm.complete(prompt=prompt)

        raw_content = response.content or ""
        final_report = _clean_report_text(raw_content)

        # Auto-continuation: If the model hit max output tokens (finish_reason == "length")
        # or stopped prematurely before concluding, request seamless continuation
        has_conclusion = any(
            sec in final_report.lower()
            for sec in ["## conclusion", "## kết luận", "## references", "## tài liệu tham khảo", "# conclusion"]
        )
        if (getattr(response, "finish_reason", None) == "length" or not has_conclusion) and len(final_report) > 500:
            tail_context = final_report[-1200:]
            cont_prompt = f"""<system_instructions>
You are continuing a research report that was cut off near the end due to token limits.
Continue writing seamlessly from where it stopped.
Do NOT repeat any already written text. Do NOT add meta-text like "(continued)".
Conclude the final points of the report.
</system_instructions>

<context_tail>
... {tail_context}
</context_tail>

Continue seamlessly:"""

            try:
                cont_response = await llm.complete(prompt=cont_prompt, max_tokens=2048)
            except TypeError:
                cont_response = await llm.complete(prompt=cont_prompt)

            cont_text = _clean_report_text(cont_response.content or "")
            if cont_text:
                cleaned_base = final_report.rstrip("- *#\n")
                final_report = f"{cleaned_base}\n\n{cont_text}"

    if not final_report:
        formatted_notes = "\n\n".join(f"- {n}" for n in notes) if notes else "- Đã hoàn tất quá trình khảo sát thông tin."
        final_report = (
            f"# Báo cáo nghiên cứu: {user_query}\n\n"
            f"## 1. Mục tiêu nghiên cứu\n\n"
            f"{getattr(brief, 'objective', user_query) or user_query}\n\n"
            f"## 2. Các phát hiện và dữ liệu đã thu thập\n\n"
            f"{formatted_notes}\n\n"
            f"## 3. Kết luận ban đầu\n\n"
            f"Báo cáo tổng hợp từ dữ liệu nghiên cứu thực tế qua các vòng khảo sát."
        )

    # Deterministically append alphabetical list of actually cited sources
    final_report = append_alphabetical_references(final_report, sources)

    sup_state["status"] = "done"
    citations_dict = registry.to_citation_dict()
    sup_state["citations"] = citations_dict

    return {
        "final_report": final_report,
        "citations": citations_dict,
        "supervisor": sup_state,
    }

