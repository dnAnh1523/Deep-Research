"""Run Deep Research Fullstack: FastAPI backend + Vite React workbench."""

import os
import subprocess
import sys
import time
import signal
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)


def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")
    env_path = os.path.join(root_dir, ".env")
    load_dotenv(dotenv_path=env_path)

    print("\n" + "=" * 70)
    print("🚀 KHỞI ĐỘNG DEEP RESEARCH FULLSTACK SYSTEM")
    print("=" * 70)

    # 1. Check local SLM lifecycle if requested
    local_slm_enabled = os.getenv("LOCAL_SLM_ENABLED", "false").lower() in ("true", "1", "yes")
    local_slm_model = os.getenv("LOCAL_SLM_MODEL", "qwen2.5:7b-instruct-q4_K_M")
    local_slm_base = os.getenv("LOCAL_SLM_BASE_URL", "http://localhost:11434/v1")

    if local_slm_enabled or ("localhost" in local_slm_base or "127.0.0.1" in local_slm_base):
        print(f"🔍 Kiểm tra Local SLM (Ollama & RTX 3050 cho {local_slm_model})...")
        try:
            from infra.ollama_manager import bootstrap_local_slm
            if bootstrap_local_slm(model_name=local_slm_model, base_url=local_slm_base):
                print(f"⚡ Local SLM ({local_slm_model}) đã sẵn sàng trên GPU!")
        except Exception as e:
            print(f"⚠️ Không thể khởi động Local SLM: {e}")

    # 2. Start Backend FastAPI (Port 8000)
    print("\n📦 Khởi động FastAPI Backend tại http://localhost:8000...")
    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "api.app:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--log-level",
        "warning",
    ]
    backend_proc = subprocess.Popen(backend_cmd, cwd=root_dir)

    # 3. Start Vite React frontend (Port 3000)
    print("🎨 Khởi động Vite React Frontend tại http://localhost:3000...")
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend_proc = subprocess.Popen([npm_cmd, "run", "dev"], cwd=frontend_dir)

    print("\n" + "-" * 70)
    print("✨ TOÀN BỘ HỆ THỐNG ĐÃ SẴN SÀNG:")
    print("   👉 Giao diện người dùng (Workbench): http://localhost:3000")
    print("   👉 API Documentation (Swagger):     http://localhost:8000/docs")
    print("   👉 Health Check:                     http://localhost:8000/health")
    print("   👉 Nhấn Ctrl + C để dừng cả 2 tiến trình.")
    print("-" * 70 + "\n")

    def handle_sigint(signum, frame):
        print("\n🛑 Đang tắt hệ thống...")
        frontend_proc.terminate()
        backend_proc.terminate()
        time.sleep(1)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_sigint)

    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                print("⚠️ Backend tiến trình đã dừng!")
                break
            if frontend_proc.poll() is not None:
                print("⚠️ Frontend tiến trình đã dừng!")
                break
    except KeyboardInterrupt:
        handle_sigint(None, None)


if __name__ == "__main__":
    main()
