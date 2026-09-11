"""Quick demo script to run an end-to-end research task."""

import asyncio
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

from graph import build_research_graph
from infra.checkpointer import get_in_memory_checkpointer
from infra.llm.factory import load_provider_config
from infra.model_router import ModelRouter, ProviderConfig
from infra.search_client import TavilySearchClient
from infra.settings import AppSettings
from infra.tracing import flush_tracing, get_langfuse_callback
from supervisor.concurrency_gate import ConcurrencyGate


async def main() -> None:
    settings = AppSettings.from_env()
    providers, fallback = load_provider_config(settings)
    missing = []
    if not providers:
        missing.append(
            "Ít nhất 1 provider/model trong config/providers.json hoặc các biến *_API_KEY + *_MODEL"
        )
    if not settings.tavily_api_key:
        missing.append("TAVILY_API_KEY (dùng cho web search)")

    if missing:
        print("\n" + "=" * 60)
        print("⚠️  CHƯA CẤU HÌNH ĐẦY ĐỦ API KEYS TRONG FILE .env:")
        for m in missing:
            print(f"  - {m}")
        print(
            "\n👉 Tạo .env và config/providers.json tại thư mục gốc "
            "(tham khảo .env.example và config/providers.example.json)."
        )
        print("=" * 60 + "\n")
        sys.exit(1)

    llm = ModelRouter(providers=providers, fallback=fallback)

    # Optional local SLM lifecycle management for users who explicitly enabled it.
    from infra.ollama_manager import bootstrap_local_slm, get_installed_model_name

    worker_llm: ModelRouter | None = None
    local_slm_model = settings.local_slm_model or "qwen2.5:7b"
    local_slm_base = settings.local_slm_base_url
    local_slm_num_ctx = int(os.getenv("LOCAL_SLM_NUM_CTX", "16384"))
    is_local_requested = settings.local_slm_enabled
    if is_local_requested:
        print(f"🔍 Đang kiểm tra môi trường Local SLM (Ollama & RTX 3050 cho {local_slm_model})...")
        local_ready = bootstrap_local_slm(
            model_name=local_slm_model,
            base_url=local_slm_base,
            enable_flash_attention=True,
        )

        if local_ready:
            actual_model = get_installed_model_name(local_slm_model, base_url=local_slm_base) or local_slm_model
            print(f"⚡ Local SLM ({actual_model}) đã sẵn sàng trên GPU! Kích hoạt Worker LLM ($0.00 / Vô hạn Tokens).")
            worker_cfg = ProviderConfig(
                provider="ollama",
                model=actual_model,
                api_key="ollama",
                api_base=local_slm_base,
                max_retries=2,
                base_delay_seconds=1.0,
                extra_params={
                    "num_ctx": local_slm_num_ctx,
                    "temperature": 0.2,
                    "repeat_penalty": 1.05,
                    "max_tokens": 1500,
                },
            )
            # Worker LLM calls local GPU model first; falls back to cloud providers
            worker_llm = ModelRouter(
                providers=[worker_cfg],
                fallback=fallback,
            )
        else:
            print("⚠️ Không thể khởi động Local SLM. Tự động fallback sang cấu hình chính.")

    search_client = TavilySearchClient(api_key=settings.tavily_api_key)
    gate = ConcurrencyGate(max_concurrent=settings.max_concurrent_researchers)
    checkpointer = get_in_memory_checkpointer()

    print("🚀 Đang khởi tạo Deep Research Graph...")
    app = build_research_graph(
        llm=llm,
        search_client=search_client,
        worker_llm=worker_llm,
        concurrency_gate=gate,
        checkpointer=checkpointer,
    )

    if len(sys.argv) > 1 and sys.argv[1].strip():
        query = sys.argv[1].strip()
    else:
        query = input("\nNhập chủ đề nghiên cứu (Enter để mặc định 'Pin thể rắn xe điện mới nhất'): ").strip()
    if not query:
        query = "Pin thể rắn xe điện mới nhất"

    clarification_history: list[str] = []
    # Trigger Clarify evaluation if query is concise/broad
    if len(query.split()) <= 15:
        print("\n" + "=" * 65)
        print("🤔 [TẦNG 1: CLARIFY EVALUATION] Đang kiểm tra tính rõ ràng của yêu cầu...")
        from clarify.node import clarify_node
        temp_state = {"user_query": query, "clarification_history": []}
        clarify_result = await clarify_node(temp_state, llm=llm)
        questions = clarify_result.get("clarification_history", [])
        if questions:
            clarify_q = questions[-1]
            print(f"❓ [CLARIFY AGENT PHÁT HIỆN YÊU CẦU CẦN LÀM RÕ]:\n   \"{clarify_q}\"")
            default_ans = "Tập trung vào tiến độ thương mại hóa của Toyota và CATL giai đoạn 2025-2026, cùng các rào cản kỹ thuật chính."
            if len(sys.argv) > 2 and sys.argv[2].strip():
                user_ans = sys.argv[2].strip()
            else:
                user_ans = input(f"\n👉 Nhập câu trả lời làm rõ (Enter để dùng: '{default_ans}'): ").strip()
            if not user_ans:
                user_ans = default_ans
            clarification_history = [clarify_q, user_ans]
            print(f"\n📝 [STATE LAYER]: Đã nạp làm rõ vào state['clarification_history'].")
            print(f"   - user_query gốc được giữ nguyên: '{query}'")
            print(f"   - Lời làm rõ nạp vào: '{user_ans}'")
            print(f"➡️ [RESEARCH BRIEF LAYER]: Tiếp theo, Brief sẽ TỔNG HỢP LẠI (rewrite) objective và sub-questions theo phạm vi làm rõ này!")
        print("=" * 65 + "\n")

    print(f"\n🔬 Bắt đầu quy trình nghiên cứu: '{query}'...")
    langfuse_handler = get_langfuse_callback()
    callbacks = [langfuse_handler] if langfuse_handler is not None else []
    if langfuse_handler is not None:
        print("🔭 Langfuse Tracing: ĐÃ KÍCH HOẠT (Traces đang được gửi về dashboard)")

    config: dict = {"configurable": {"thread_id": "demo_session"}}
    if callbacks:
        config["callbacks"] = callbacks

    input_state = {
        "user_query": query,
        "clarification_history": clarification_history,
    }
    final_report = ""

    step_start = time.perf_counter()
    overall_start = time.perf_counter()
    prev_brain_count = 0
    prev_worker_count = 0
    process_timeline = []

    try:
        async for event in app.astream(input_state, config=config, stream_mode="updates"):
            step_latency = round(time.perf_counter() - step_start, 2)
            step_start = time.perf_counter()
            new_calls_brain = llm.call_history[prev_brain_count:]
            prev_brain_count = len(llm.call_history)

            new_calls_worker = worker_llm.call_history[prev_worker_count:] if worker_llm else []
            if worker_llm:
                prev_worker_count = len(worker_llm.call_history)

            new_calls = new_calls_brain + new_calls_worker

            step_cost = sum(c.cost_usd for c in new_calls)
            step_prompt_toks = sum(c.prompt_tokens for c in new_calls)
            step_compl_toks = sum(c.completion_tokens for c in new_calls)
            step_total_toks = sum(c.total_tokens for c in new_calls)

            if new_calls:
                models_used = ", ".join(list(dict.fromkeys(f"{c.provider}/{c.model}" for c in new_calls)))
                telemetry_tag = f"⏱️ {step_latency}s | 🤖 {models_used} | 💰 ${step_cost:.6f}"
            else:
                models_used = "Rule-based"
                telemetry_tag = f"⏱️ {step_latency}s"

            for node_name, node_output in event.items():
                process_timeline.append({
                    "node": node_name,
                    "models": models_used,
                    "latency_seconds": step_latency,
                    "prompt_tokens": step_prompt_toks,
                    "completion_tokens": step_compl_toks,
                    "total_tokens": step_total_toks,
                    "cost_usd": step_cost,
                })

                if node_name == "session_check":
                    print(f"  [1/8] ✅ Session Check ({telemetry_tag}): Khởi tạo phiên hợp lệ", flush=True)
                elif node_name == "intent_arbitrator":
                    intent = node_output.get("intent", "RESEARCH") if isinstance(node_output, dict) else "RESEARCH"
                    print(f"  [2/8] 🧭 Intent Arbitrator ({telemetry_tag}): Ý định = '{intent}'", flush=True)
                elif node_name == "semantic_cache":
                    hit = node_output.get("cache_hit", False) if isinstance(node_output, dict) else False
                    print(f"  [3/8] 💾 Semantic Cache ({telemetry_tag}): {'🎯 HIT (Lấy từ bộ nhớ cache)' if hit else 'Miss (tiến hành nghiên cứu mới)'}", flush=True)
                elif node_name == "clarify":
                    print(f"  [4/8] 💬 Clarify ({telemetry_tag}): Làm rõ bối cảnh câu hỏi", flush=True)
                elif node_name == "research_brief":
                    brief = node_output.get("supervisor", {}).get("brief") if isinstance(node_output, dict) else None
                    if brief:
                        sub_qs = getattr(brief, "sub_questions", [])
                        print(f"  [5/8] 📋 Research Brief ({telemetry_tag}): Đã lập kế hoạch ({len(sub_qs)} mục tiêu cụ thể):", flush=True)
                        for idx, q in enumerate(sub_qs, 1):
                            print(f"        {idx}. {q}", flush=True)
                    else:
                        print(f"  [5/8] 📋 Research Brief ({telemetry_tag}): Đã lập kế hoạch nghiên cứu", flush=True)
                elif node_name == "supervisor":
                    sup = node_output.get("supervisor", {}) if isinstance(node_output, dict) else {}
                    rnd = sup.get("current_round", 1)
                    status = sup.get("status", "delegating")
                    guidance = sup.get("research_guidance")
                    follow_ups = sup.get("follow_up_queries", [])
                    print(f"  [6/8] 👑 Supervisor ({telemetry_tag}): Vòng {rnd} — Trạng thái: {status}", flush=True)
                    if guidance and status == "delegating":
                        print(f"        🧠 Gap Analysis: {guidance}", flush=True)
                    if follow_ups and rnd > 1:
                        print(f"        🎯 Phân bổ {len(follow_ups)} truy vấn mới cho Vòng {rnd}:", flush=True)
                        for f_idx, fq in enumerate(follow_ups, 1):
                            print(f"           {f_idx}. {fq}", flush=True)
                elif node_name == "researcher":
                    findings = node_output.get("raw_findings", []) if isinstance(node_output, dict) else []
                    visited = node_output.get("visited_urls", []) if isinstance(node_output, dict) else []
                    print(f"  🔍 Researcher Pool ({telemetry_tag}): Đã trích xuất {len(findings)} tư liệu ({len(visited)} URL mới)", flush=True)
                    for u in visited[:3]:
                        print(f"        🌐 Source: {u}", flush=True)
                elif node_name == "compression":
                    sup = node_output.get("supervisor", {}) if isinstance(node_output, dict) else {}
                    notes = sup.get("compressed_notes", [])
                    print(f"  ⚡ Compression ({telemetry_tag}): Đã cô đọng tri thức ({len(notes)} luận điểm trong sổ tay)", flush=True)
                elif node_name == "verification":
                    print(f"  [7/8] 🛡️ Citation Verifier ({telemetry_tag}): Kiểm chứng trích dẫn chéo hoàn tất", flush=True)
                elif node_name == "reporting":
                    if isinstance(node_output, dict) and "final_report" in node_output:
                        final_report = node_output["final_report"]
                    print(f"  [8/8] 📝 Reporting ({telemetry_tag}): Đã tổng hợp xong toàn bộ báo cáo nghiên cứu!", flush=True)
                elif node_name in ("out_of_scope", "meta_command"):
                    if isinstance(node_output, dict) and "final_report" in node_output:
                        final_report = node_output["final_report"]
    finally:
        flush_tracing(langfuse_handler)

    total_run_latency = round(time.perf_counter() - overall_start, 2)
    telemetry = llm.get_telemetry_summary()
    if worker_llm is not None:
        worker_telemetry = worker_llm.get_telemetry_summary()
        telemetry["total_calls"] += worker_telemetry["total_calls"]
        telemetry["total_latency_seconds"] = round(telemetry["total_latency_seconds"] + worker_telemetry["total_latency_seconds"], 2)
        telemetry["total_prompt_tokens"] += worker_telemetry["total_prompt_tokens"]
        telemetry["total_completion_tokens"] += worker_telemetry["total_completion_tokens"]
        telemetry["total_tokens"] += worker_telemetry["total_tokens"]
        telemetry["total_cost_usd"] = round(telemetry["total_cost_usd"] + worker_telemetry["total_cost_usd"], 6)
        for mod, stats in worker_telemetry.get("by_model", {}).items():
            if mod not in telemetry["by_model"]:
                telemetry["by_model"][mod] = stats
            else:
                telemetry["by_model"][mod]["calls"] += stats["calls"]
                telemetry["by_model"][mod]["latency_seconds"] = round(telemetry["by_model"][mod]["latency_seconds"] + stats["latency_seconds"], 2)
                telemetry["by_model"][mod]["total_tokens"] += stats["total_tokens"]
                telemetry["by_model"][mod]["cost_usd"] = round(telemetry["by_model"][mod]["cost_usd"] + stats["cost_usd"], 6)

    if final_report:
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "latest_report.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_report)
        print(f"\n💾 Đã tự động lưu bài báo cáo đầy đủ vào: {output_path}", flush=True)

    print("\n" + "=" * 105)
    print("📊 BẢNG TỔNG KẾT HIỆU NĂNG TỪNG QUÁ TRÌNH & CHI PHÍ THƯƠNG MẠI PAY-AS-YOU-GO")
    print("=" * 105)
    header = f"{'Giai đoạn / Tiến trình':<24} | {'Model thực tế':<34} | {'Latency':<9} | {'Tokens (In/Out/Tot)':<20} | {'Pay-As-You-Go':<12}"
    print(header)
    print("-" * 105)
    pretty_names = {
        "session_check": "1. Session Check",
        "intent_arbitrator": "2. Intent Arbitrator",
        "semantic_cache": "3. Semantic Cache",
        "clarify": "4. Clarify",
        "research_brief": "5. Research Brief",
        "supervisor": "6. Supervisor",
        "researcher": "   ↳ Researcher Pool",
        "compression": "   ↳ Compression",
        "verification": "7. Citation Verifier",
        "reporting": "8. Reporting",
        "out_of_scope": "Out of Scope",
        "meta_command": "Meta Command",
    }
    for p in process_timeline:
        tok_str = f"{p['prompt_tokens']}/{p['completion_tokens']}/{p['total_tokens']}" if p['total_tokens'] > 0 else "-"
        cost_str = f"${p['cost_usd']:.6f}" if p['cost_usd'] > 0 else "$0.000000"
        name_str = pretty_names.get(p['node'], p['node'])
        model_display = p['models'][:32]
        row = f"{name_str:<24} | {model_display:<34} | {p['latency_seconds']:>6.2f}s  | {tok_str:<20} | {cost_str:<12}"
        print(row)

    print("-" * 105)
    print(f"⏱️  TỔNG THỜI GIAN TOÀN TRÌNH (End-to-End Latency): {total_run_latency:.2f} giây (Thời gian mạng LLM: {telemetry['total_latency_seconds']:.2f}s)")
    print(f"🔢 TỔNG SỐ TOKEN TIÊU THỤ: Prompt: {telemetry['total_prompt_tokens']:,} | Completion: {telemetry['total_completion_tokens']:,} | Tổng: {telemetry['total_tokens']:,}")
    print(f"💰 GIÁ TRỊ TÍNH TOÁN PAY-AS-YOU-GO: ${telemetry['total_cost_usd']:.6f} USD")
    print(
        "🎉 CHI PHÍ THỰC TẾ: phụ thuộc provider/model đã cấu hình; "
        "unknown pricing được đánh dấu riêng."
    )

    if len(telemetry["by_model"]) > 1:
        print("\n📌 CHI TIẾT THEO TỪNG MODEL PHỤC VỤ (Phân bổ theo model thực tế):")
        for mod, stats in telemetry["by_model"].items():
            print(f"  • {mod:<38}: {stats['calls']} calls | {stats['latency_seconds']:.2f}s | {stats['total_tokens']:,} toks | ${stats['cost_usd']:.6f}")
    print("=" * 105 + "\n")

    print("=" * 60)
    print("📋 KẾT QUẢ BÁO CÁO NGHIÊN CỨU HOÀN THÀNH:")
    print("=" * 60)
    print(final_report or "Không có báo cáo.")


if __name__ == "__main__":
    asyncio.run(main())
