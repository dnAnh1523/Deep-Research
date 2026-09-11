"""Tests for Module 8: API Layer."""

import asyncio
import json
from api.app import create_app
import httpx
import pytest


class MockGraph:
    """Mock compiled graph recording invocations and yielding stream events."""

    def __init__(self) -> None:
        self.invocations: list[dict] = []
        self.last_config: dict = {}

    async def ainvoke(self, input_state: dict, config: dict | None = None) -> dict:
        self.invocations.append(input_state)
        self.last_config = config or {}
        return {
            "final_report": "# Test Report on " + input_state.get("user_query", ""),
            "supervisor": {"status": "done"},
        }

    async def astream(self, input_state: dict, config: dict | None = None, stream_mode: str = "updates"):
        self.invocations.append(input_state)
        self.last_config = config or {}
        yield {"step": "clarify", "data": "Clarifying query"}
        await asyncio.sleep(0.01)
        yield {"step": "brief", "data": "Brief established"}
        await asyncio.sleep(0.01)
        yield {"step": "reporting", "data": "Final report generated"}


def test_health_endpoint():
    async def run():
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/health")
            assert res.status_code == 200
            assert res.json()["status"] == "ok"

    asyncio.run(run())


def test_session_id_auto_generated_when_missing():
    async def run():
        mock_graph = MockGraph()
        app = create_app(graph=mock_graph)
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/research", json={"query": "Quantum AI"})
            assert res.status_code == 200
            data = res.json()
            session_id = data.get("session_id")
            assert session_id is not None
            assert len(session_id) > 10
            # Header and cookie also returned
            assert res.headers.get("X-Session-ID") == session_id
            assert "session_id" in res.cookies

            # Verify thread_id in graph config equals session_id directly (1-1 mapping)
            assert mock_graph.last_config["configurable"]["thread_id"] == session_id
            assert mock_graph.invocations[0]["thread_id"] == session_id

    asyncio.run(run())


def test_session_id_preserved_from_header():
    async def run():
        mock_graph = MockGraph()
        app = create_app(graph=mock_graph)
        transport = httpx.ASGITransport(app=app)
        custom_session = "custom_session_abc_123"

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/research",
                json={"query": "Neural Radiance Fields"},
                headers={"X-Session-ID": custom_session},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["session_id"] == custom_session
            assert mock_graph.last_config["configurable"]["thread_id"] == custom_session

    asyncio.run(run())


def test_session_id_preserved_from_cookie():
    async def run():
        mock_graph = MockGraph()
        app = create_app(graph=mock_graph)
        transport = httpx.ASGITransport(app=app)
        cookie_session = "cookie_session_xyz_789"

        async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"session_id": cookie_session}) as client:
            res = await client.post(
                "/research",
                json={"query": "Gaussian Splatting"},
            )
            assert res.status_code == 200
            assert res.json()["session_id"] == cookie_session
            assert mock_graph.last_config["configurable"]["thread_id"] == cookie_session

    asyncio.run(run())


def test_sse_streaming_endpoint_receives_chunks():
    async def run():
        mock_graph = MockGraph()
        app = create_app(graph=mock_graph)
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream("POST", "/research/stream", json={"query": "Diffusion Models"}) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

                lines = []
                async for line in response.aiter_lines():
                    if line.strip():
                        lines.append(line.strip())

                assert len(lines) >= 3
                assert any("clarify" in line for line in lines)
                assert any("reporting" in line for line in lines)

    asyncio.run(run())


def test_get_latest_report_endpoint():
    """Verify /api/latest-report returns available report if file exists."""
    async def run():
        app = create_app()
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/latest-report")
            assert res.status_code == 200
            data = res.json()
            assert "status" in data
            assert data["status"] in ("available", "not_found")
            if data["status"] == "available":
                assert len(data["report"]) > 0

    asyncio.run(run())


def test_get_latest_report_uses_configured_storage_dir(monkeypatch, tmp_path):
    """The compatibility endpoint follows REPORT_STORAGE_DIR instead of repo root."""
    report_path = tmp_path / "latest_report.md"
    report_path.write_text("# Stored report\n\nSource [1](https://example.com)", encoding="utf-8")
    monkeypatch.setenv("REPORT_STORAGE_DIR", str(tmp_path))

    async def run():
        app = create_app()
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/latest-report")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "available"
            assert data["report"].startswith("# Stored report")

    asyncio.run(run())
