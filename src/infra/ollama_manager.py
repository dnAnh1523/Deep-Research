"""Local Ollama Lifecycle Manager for Deep Research Agent.

Provides zero-touch automated lifecycle management for local SLM:
1. Locates the local Ollama binary across platforms (Windows / Linux / macOS).
2. Auto-starts `ollama serve` with OLLAMA_FLASH_ATTENTION=1 in a detached process if not running.
3. Performs non-blocking health checks on http://localhost:11434.
4. Auto-checks and pulls local GGUF models with streaming progress indicators.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def find_ollama_binary() -> str | None:
    """Find the ollama executable binary on the host system.

    Checks PATH first, then scans standard installation directories on Windows, macOS, and Linux.
    """
    # 1. Check system PATH
    found = shutil.which("ollama") or shutil.which("ollama.exe")
    if found:
        return found

    # 2. Check standard Windows locations
    if sys.platform == "win32":
        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Ollama\ollama.exe"),
            os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
        ]
        for path in candidates:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

    # 3. Check standard Unix / macOS locations
    unix_candidates = [
        "/usr/local/bin/ollama",
        "/usr/bin/ollama",
        "/opt/homebrew/bin/ollama",
        os.path.expanduser("~/.local/bin/ollama"),
    ]
    for path in unix_candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    return None


def clean_base_url(base_url: str) -> str:
    """Normalize base URL by stripping trailing slashes and /v1 suffix."""
    url = base_url.strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def is_ollama_running(base_url: str = "http://localhost:11434", timeout_seconds: float = 0.5) -> bool:
    """Check if Ollama server is responding to HTTP requests."""
    root_url = clean_base_url(base_url)
    endpoint = f"{root_url}/api/tags"
    try:
        req = urllib.request.Request(endpoint, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_ollama_running(
    base_url: str = "http://localhost:11434",
    timeout_seconds: float = 6.0,
    enable_flash_attention: bool = True,
) -> bool:
    """Ensure that the local Ollama daemon is running. If not, auto-start it in background.

    Args:
        base_url: The root or v1 URL of Ollama (e.g. http://localhost:11434).
        timeout_seconds: Maximum seconds to wait for server readiness.
        enable_flash_attention: Inject OLLAMA_FLASH_ATTENTION=1 for GPU speedup (e.g. modern NVIDIA GPUs).

    Returns:
        True if server is running and healthy, False otherwise.
    """
    if is_ollama_running(base_url, timeout_seconds=0.5):
        return True

    binary = find_ollama_binary()
    if not binary:
        logger.warning("Ollama binary not found on this machine. Cannot auto-start Ollama daemon.")
        return False

    env = os.environ.copy()
    if enable_flash_attention:
        env["OLLAMA_FLASH_ATTENTION"] = "1"

    hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
    if hf_token:
        env["HF_TOKEN"] = hf_token
        env["HUGGING_FACE_HUB_TOKEN"] = hf_token
        logger.info("Injected HF_TOKEN into local Ollama daemon environment.")

    logger.info("Auto-starting local Ollama daemon (%s) with OLLAMA_FLASH_ATTENTION=%s...", binary, env.get("OLLAMA_FLASH_ATTENTION"))

    try:
        if sys.platform == "win32":
            creationflags = 0
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
            if hasattr(subprocess, "DETACHED_PROCESS"):
                creationflags |= subprocess.DETACHED_PROCESS

            subprocess.Popen(
                [binary, "serve"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        else:
            subprocess.Popen(
                [binary, "serve"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except Exception as exc:
        logger.error("Failed to spawn Ollama daemon: %s", exc)
        return False

    # Poll server until ready or timed out
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < timeout_seconds:
        time.sleep(0.3)
        if is_ollama_running(base_url, timeout_seconds=0.5):
            logger.info("Local Ollama daemon is ready and responding on %s.", base_url)
            return True

    logger.warning("Timed out after %.1fs waiting for Ollama daemon to start.", timeout_seconds)
    return False


def resolve_model_candidates(model_name: str) -> list[str]:
    """Resolve a user-specified model identifier into prioritized candidate tags across Hugging Face & Ollama.

    If given a Qwen2.5-7B variant, generates:
    1. Direct single-file Hugging Face GGUF Q4_K_M (bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M)
    2. Official Ollama registry Q4_K_M build (qwen2.5:7b)
    3. User requested exact identifier
    """
    cleaned = model_name.strip()
    candidates: list[str] = [cleaned]

    # If it's already an explicit Hugging Face or registry tag, keep as primary
    if cleaned.startswith("hf.co/") or cleaned.startswith("huggingface.co/"):
        return candidates

    lower = cleaned.lower()
    if "qwen2.5" in lower and "7b" in lower:
        # 1. Hugging Face Hub direct single-file GGUF Q4_K_M (top reliability on consumer GPUs)
        hf_candidate = "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M"
        # 2. Ollama official library Q4_K_M (4.7GB, identical weights)
        ollama_candidate = "qwen2.5:7b"

        for cand in [hf_candidate, ollama_candidate]:
            if cand not in candidates:
                candidates.append(cand)
    elif "qwen2.5" in lower and "3b" in lower:
        candidates.extend([
            "hf.co/bartowski/Qwen2.5-3B-Instruct-GGUF:Q4_K_M",
            "qwen2.5:3b",
        ])

    return candidates


def is_model_installed(model_name: str, base_url: str = "http://localhost:11434") -> bool:
    """Check whether a specific model or any of its compatible candidates is present in local Ollama."""
    return get_installed_model_name(model_name, base_url=base_url) is not None


def get_installed_model_name(model_name: str, base_url: str = "http://localhost:11434") -> str | None:
    """Find the exact tag name of an installed model matching the request or its candidates.

    Returns the actual installed tag string (e.g. 'hf.co/bartowski/...:Q4_K_M' or 'qwen2.5:7b')
    or None if no compatible model is found.
    """
    root_url = clean_base_url(base_url)
    endpoint = f"{root_url}/api/tags"
    try:
        req = urllib.request.Request(endpoint, method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            installed_models = [m.get("name", "") for m in data.get("models", [])]

            candidates = resolve_model_candidates(model_name)

            for cand in candidates:
                cand_lower = cand.lower().strip()
                cand_core = cand_lower.split("/")[-1].split(":")[0]

                for installed in installed_models:
                    inst_lower = installed.lower().strip()
                    # 1. Exact match
                    if inst_lower == cand_lower or inst_lower == f"{cand_lower}:latest":
                        return installed

                    # 2. Hugging Face repository and tag matching
                    if "hf.co/" in cand_lower and cand_lower.split("hf.co/")[-1] in inst_lower:
                        return installed

                    # 3. Family matching for Qwen 7B
                    if "qwen2.5" in cand_lower and "7b" in cand_lower:
                        if "qwen2.5" in inst_lower and "7b" in inst_lower:
                            return installed

                    # 4. Prefix match
                    if ":" in cand_lower and inst_lower.startswith(cand_lower):
                        return installed

            return None
    except Exception as exc:
        logger.debug("Failed to query Ollama tags: %s", exc)
        return None


def _pull_single_model_api(
    model_tag: str,
    base_url: str,
    stream_progress: bool = True,
) -> bool:
    """Attempt pulling a single model tag from registry (supports both Ollama library and hf.co)."""
    root_url = clean_base_url(base_url)
    pull_endpoint = f"{root_url}/api/pull"
    payload = json.dumps({"name": model_tag, "stream": True}).encode("utf-8")

    source_desc = "Hugging Face Hub" if "hf.co" in model_tag else "Ollama Registry"
    print(f"📥 Đang thử tải từ {source_desc}: '{model_tag}'...", flush=True)

    try:
        req = urllib.request.Request(
            pull_endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        last_pct = -1
        with urllib.request.urlopen(req, timeout=3600.0) as resp:
            for line in resp:
                if not line.strip():
                    continue
                chunk = json.loads(line.decode("utf-8"))

                # Check for explicit registry error chunks (e.g. 400 sharded GGUF or 404 not found)
                if "error" in chunk:
                    err_msg = chunk["error"]
                    logger.warning("Pull chunk reported error for '%s': %s", model_tag, err_msg)
                    print(f"\n⚠️ Lỗi registry khi tải '{model_tag}': {err_msg}", flush=True)
                    return False

                status = chunk.get("status", "")
                completed = chunk.get("completed", 0)
                total = chunk.get("total", 0)

                if stream_progress and total > 0:
                    pct = int((completed / total) * 100)
                    if pct != last_pct and pct % 5 == 0:
                        last_pct = pct
                        mb_done = completed / (1024 * 1024)
                        mb_tot = total / (1024 * 1024)
                        print(f"   ↳ {status}: {mb_done:.1f}MB / {mb_tot:.1f}MB ({pct}%)", end="\r", flush=True)

                if status == "success":
                    print(f"\n✅ Tải thành công '{model_tag}'!", flush=True)
                    return True

        return is_model_installed(model_tag, base_url)
    except Exception as exc:
        logger.warning("API pull failed for '%s': %s", model_tag, exc)
        return False


def download_hf_gguf_and_create_model(
    repo_id: str = "bartowski/Qwen2.5-7B-Instruct-GGUF",
    filename: str = "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
    target_model_name: str = "qwen2.5:7b-instruct-q4_K_M",
    base_url: str = "http://localhost:11434",
    num_ctx: int = 16384,
) -> bool:
    """Fallback: Direct download via huggingface_hub Python library + `ollama create` Modelfile."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        logger.warning("huggingface_hub is not installed; skipping direct GGUF download.")
        return False

    binary = find_ollama_binary()
    if not binary:
        return False

    print(f"🌐 Kích hoạt kênh tải trực tiếp Hugging Face Hub: {repo_id}/{filename}...", flush=True)
    models_dir = os.path.join(os.getcwd(), "models")
    os.makedirs(models_dir, exist_ok=True)

    try:
        hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
        file_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=models_dir,
            token=hf_token,
        )
        print(f"📦 Đã tải file GGUF về: {file_path}", flush=True)

        # Create temporary Modelfile
        modelfile_content = (
            f'FROM "{file_path}"\n'
            f"PARAMETER num_ctx {num_ctx}\n"
            f"PARAMETER temperature 0.2\n"
            f"PARAMETER repeat_penalty 1.05\n"
        )
        modelfile_path = os.path.join(models_dir, "Modelfile.local")
        with open(modelfile_path, "w", encoding="utf-8") as f:
            f.write(modelfile_content)

        print(f"🔨 Đang đăng ký model vào Ollama: 'ollama create {target_model_name}'...", flush=True)
        res = subprocess.run(
            [binary, "create", target_model_name, "-f", modelfile_path],
            check=True,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            print(f"✅ Đã tạo model local '{target_model_name}' thành công từ Hugging Face GGUF!", flush=True)
            return True
        return False
    except Exception as exc:
        logger.error("Failed to direct-download and create from Hugging Face: %s", exc)
        return False


def ensure_model_installed(
    model_name: str,
    base_url: str = "http://localhost:11434",
    stream_progress: bool = True,
) -> bool:
    """Ensure the target model is installed locally, with Hugging Face & Ollama multi-source fallbacks."""
    installed = get_installed_model_name(model_name, base_url)
    if installed is not None:
        logger.info("Model '%s' (resolved as '%s') already installed locally.", model_name, installed)
        return True

    candidates = resolve_model_candidates(model_name)
    logger.info("Model '%s' not found locally. Candidate tags to try: %s", model_name, candidates)
    print(f"🔍 Model '{model_name}' chưa có trên máy. Bắt đầu tìm kiếm từ Hugging Face & Ollama...", flush=True)

    # 1. Try pulling candidates via Ollama API
    for cand in candidates:
        success = _pull_single_model_api(cand, base_url=base_url, stream_progress=stream_progress)
        if success:
            return True

    # 2. Fallback to CLI execution if available
    binary = find_ollama_binary()
    if binary:
        cli_env = os.environ.copy()
        hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
        if hf_token:
            cli_env["HF_TOKEN"] = hf_token
            cli_env["HUGGING_FACE_HUB_TOKEN"] = hf_token

        for cand in candidates:
            try:
                print(f"⚡ Thử lại với Ollama CLI: ollama pull {cand}...", flush=True)
                res = subprocess.run([binary, "pull", cand], env=cli_env, check=False)
                if res.returncode == 0 and is_model_installed(model_name, base_url):
                    return True
            except Exception as cli_exc:
                logger.error("CLI pull failed for %s: %s", cand, cli_exc)

    # 3. Third-tier fallback: Direct download from Hugging Face Hub + ollama create
    lower = model_name.lower()
    if "qwen2.5" in lower and "7b" in lower:
        return download_hf_gguf_and_create_model(
            repo_id="bartowski/Qwen2.5-7B-Instruct-GGUF",
            filename="Qwen2.5-7B-Instruct-Q4_K_M.gguf",
            target_model_name=model_name,
            base_url=base_url,
        )

    return False


def bootstrap_local_slm(
    model_name: str = "qwen2.5:7b-instruct-q4_K_M",
    base_url: str = "http://localhost:11434",
    enable_flash_attention: bool = True,
) -> bool:
    """One-click orchestrator for local SLM environment:

    1. Checks/starts Ollama server with Flash Attention on GPU.
    2. Checks/pulls the required GGUF model from Hugging Face Hub or Ollama.
    3. Returns True if fully ready, allowing seamless worker activation.
    """
    # Step 1: Ensure Ollama server is up
    server_ready = ensure_ollama_running(
        base_url=base_url,
        timeout_seconds=6.0,
        enable_flash_attention=enable_flash_attention,
    )
    if not server_ready:
        return False

    # Step 2: Ensure model is present locally
    model_ready = ensure_model_installed(
        model_name=model_name,
        base_url=base_url,
        stream_progress=True,
    )
    return model_ready

