"""Unit tests for infra.ollama_manager (Automated Local SLM Lifecycle Management)."""

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

from infra.ollama_manager import (
    _pull_single_model_api,
    bootstrap_local_slm,
    clean_base_url,
    ensure_model_installed,
    ensure_ollama_running,
    find_ollama_binary,
    get_installed_model_name,
    is_model_installed,
    is_ollama_running,
    resolve_model_candidates,
)


def test_clean_base_url():
    assert clean_base_url("http://localhost:11434/v1") == "http://localhost:11434"
    assert clean_base_url("http://localhost:11434/") == "http://localhost:11434"
    assert clean_base_url("http://127.0.0.1:11434/v1/") == "http://127.0.0.1:11434"


def test_find_ollama_binary():
    with patch("shutil.which", return_value="C:\\Fake\\ollama.exe"):
        assert find_ollama_binary() == "C:\\Fake\\ollama.exe"

    with patch("shutil.which", return_value=None), patch("os.path.isfile", return_value=False):
        assert find_ollama_binary() is None


def test_is_ollama_running_healthy():
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.status = 200
    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert is_ollama_running("http://localhost:11434") is True


def test_is_ollama_running_unreachable():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        assert is_ollama_running("http://localhost:11434") is False


def test_ensure_ollama_running_when_already_active():
    with patch("infra.ollama_manager.is_ollama_running", return_value=True), \
         patch("subprocess.Popen") as mock_popen:
        result = ensure_ollama_running()
        assert result is True
        mock_popen.assert_not_called()


def test_ensure_ollama_running_spawns_process_with_flash_attention():
    is_running_states = [False, False, True]

    def mock_check(*args, **kwargs):
        return is_running_states.pop(0) if is_running_states else True

    with patch("infra.ollama_manager.is_ollama_running", side_effect=mock_check), \
         patch("infra.ollama_manager.find_ollama_binary", return_value="C:\\Programs\\ollama.exe"), \
         patch("subprocess.Popen") as mock_popen, \
         patch("time.sleep"):
        result = ensure_ollama_running(timeout_seconds=2.0, enable_flash_attention=True)
        assert result is True
        assert mock_popen.called
        call_args, call_kwargs = mock_popen.call_args
        assert call_args[0] == ["C:\\Programs\\ollama.exe", "serve"]
        assert call_kwargs["env"]["OLLAMA_FLASH_ATTENTION"] == "1"


def test_ensure_ollama_running_fails_when_binary_missing():
    with patch("infra.ollama_manager.is_ollama_running", return_value=False), \
         patch("infra.ollama_manager.find_ollama_binary", return_value=None):
        assert ensure_ollama_running() is False


def test_is_model_installed():
    tags_data = json.dumps({
        "models": [
            {"name": "qwen2.5:7b-instruct-q4_K_M"},
            {"name": "llama3.1:8b"},
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = tags_data

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert is_model_installed("qwen2.5:7b-instruct-q4_K_M") is True
        assert is_model_installed("qwen2.5:7b") is True  # Alias match
        assert is_model_installed("gemma2:9b") is False


def test_ensure_model_installed_already_present():
    with patch("infra.ollama_manager.get_installed_model_name", return_value="qwen2.5:7b"), \
         patch("urllib.request.urlopen") as mock_urlopen:
        assert ensure_model_installed("qwen2.5:7b") is True
        mock_urlopen.assert_not_called()


def test_ensure_model_installed_pulls_successfully():
    is_installed_states = [False, True]

    def mock_installed(*args, **kwargs):
        return is_installed_states.pop(0) if is_installed_states else True

    stream_lines = [
        json.dumps({"status": "downloading", "total": 1000, "completed": 500}).encode("utf-8") + b"\n",
        json.dumps({"status": "success"}).encode("utf-8") + b"\n",
    ]

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = io.BytesIO(b"".join(stream_lines))
    mock_resp.__exit__.return_value = None

    with patch("infra.ollama_manager.is_model_installed", side_effect=mock_installed), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        assert ensure_model_installed("qwen2.5:7b-instruct-q4_K_M", stream_progress=False) is True


def test_bootstrap_local_slm_full_success():
    with patch("infra.ollama_manager.ensure_ollama_running", return_value=True), \
         patch("infra.ollama_manager.ensure_model_installed", return_value=True):
        assert bootstrap_local_slm("qwen2.5:7b-instruct-q4_K_M") is True


def test_bootstrap_local_slm_fails_if_server_unavailable():
    with patch("infra.ollama_manager.ensure_ollama_running", return_value=False):
        assert bootstrap_local_slm("qwen2.5:7b-instruct-q4_K_M") is False


def test_resolve_model_candidates():
    # 1. Standard Qwen2.5 7B generates both Hugging Face GGUF and Ollama registry tags
    cands = resolve_model_candidates("qwen2.5:7b-instruct-q4_K_M")
    assert "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M" in cands
    assert "qwen2.5:7b" in cands
    assert "qwen2.5:7b-instruct-q4_K_M" in cands

    # 2. Explicit Hugging Face tag stays as sole primary
    hf_cands = resolve_model_candidates("hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M")
    assert hf_cands == ["hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M"]


def test_get_installed_model_name():
    tags_data = json.dumps({
        "models": [
            {"name": "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M"},
            {"name": "llama3.1:8b"},
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = tags_data

    with patch("urllib.request.urlopen", return_value=mock_resp):
        # Finds matching Hugging Face tag when querying generic name
        matched = get_installed_model_name("qwen2.5:7b-instruct-q4_K_M")
        assert matched == "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M"

        # Direct tag match
        matched_direct = get_installed_model_name("llama3.1:8b")
        assert matched_direct == "llama3.1:8b"

        # Non-installed model returns None
        assert get_installed_model_name("phi3:mini") is None


def test_pull_single_model_api_aborts_on_registry_error():
    stream_lines = [
        json.dumps({"status": "pulling manifest"}).encode("utf-8") + b"\n",
        json.dumps({"error": "pull model manifest: 400: This tag is a sharded GGUF"}).encode("utf-8") + b"\n",
    ]

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = io.BytesIO(b"".join(stream_lines))
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        success = _pull_single_model_api(
            model_tag="hf.co/Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M",
            base_url="http://localhost:11434",
            stream_progress=False,
        )
        assert success is False

