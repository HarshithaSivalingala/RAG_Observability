"""
test_api.py — FastAPI route tests and session handling.

Fix: Use anyio backend with proper async lifecycle instead of
relying on TestClient's lifespan which conflicts with aiosqlite.
"""

import asyncio
import json
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# ── App fixture with fresh DB ─────────────────────────────────────────────────
@pytest_asyncio.fixture
async def async_client(tmp_path, monkeypatch):
    """
    Create an AsyncClient with a fresh database for each test.
    Uses httpx.AsyncClient with ASGITransport to avoid lifespan conflicts.
    Manually initializes and closes the DB around each test.
    """
    import database
    import main

    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database._db = None

    # Initialize DB manually — don't rely on lifespan
    await database.init_db()

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await database.close_db()


@pytest_asyncio.fixture
async def async_client_with_data(async_client):
    """Client pre-populated with one saved query."""
    import database

    await database.save_query(
        request_id="route-test-001",
        session_id="session-abc",
        question="What is the Holloway portfolio value?",
        response="The portfolio value is $4,820,350.",
        total_latency_ms=1200.5,
        retrieval_latency_ms=150.0,
        llm_latency_ms=1050.5,
        chunks_retrieved=2,
        chunk_scores=[0.92, 0.87],
        chunk_titles=["report.pdf", "memo.pdf"],
        cache_hit=False,
        error=None,
        error_type=None,
        query_category="financial",
    )
    return async_client


# ── Health Endpoint ───────────────────────────────────────────────────────────
class TestHealthEndpoint:

    async def test_returns_200(self, async_client):
        response = await async_client.get("/observability/health")
        assert response.status_code == 200

    async def test_returns_healthy_status(self, async_client):
        data = (await async_client.get("/observability/health")).json()
        assert data["status"] == "healthy"

    async def test_includes_proxy_target(self, async_client):
        data = (await async_client.get("/observability/health")).json()
        assert "proxy_target" in data
        assert data["proxy_target"] == "http://localhost:8000"

    async def test_includes_cache_entries_count(self, async_client):
        data = (await async_client.get("/observability/health")).json()
        assert "cache_entries" in data
        assert isinstance(data["cache_entries"], int)

    async def test_includes_timestamp(self, async_client):
        data = (await async_client.get("/observability/health")).json()
        assert "timestamp" in data


# ── Metrics Endpoint ──────────────────────────────────────────────────────────
class TestMetricsEndpoint:

    async def test_returns_200(self, async_client):
        assert (await async_client.get("/observability/metrics")).status_code == 200

    async def test_returns_zero_metrics_on_empty_db(self, async_client):
        data = (await async_client.get("/observability/metrics")).json()
        assert data["total_queries"] == 0
        assert data["avg_latency_ms"] == 0.0
        assert data["p95_latency_ms"] == 0.0
        assert data["error_rate"] == 0.0

    async def test_returns_correct_metrics_with_data(self, async_client_with_data):
        data = (await async_client_with_data.get("/observability/metrics")).json()
        assert data["total_queries"] == 1
        assert data["avg_latency_ms"] == 1200.5

    async def test_response_has_all_required_fields(self, async_client):
        data = (await async_client.get("/observability/metrics")).json()
        required = {
            "total_queries", "avg_latency_ms", "p50_latency_ms",
            "p95_latency_ms", "error_rate", "cache_hit_rate",
            "slow_query_count", "empty_response_count",
        }
        assert required.issubset(data.keys())


# ── Queries Endpoint ──────────────────────────────────────────────────────────
class TestQueriesEndpoint:

    async def test_returns_200(self, async_client):
        assert (await async_client.get("/observability/queries")).status_code == 200

    async def test_returns_empty_list_on_empty_db(self, async_client):
        data = (await async_client.get("/observability/queries")).json()
        assert data == []

    async def test_returns_saved_query(self, async_client_with_data):
        data = (await async_client_with_data.get("/observability/queries")).json()
        assert len(data) == 1
        assert data[0]["id"] == "route-test-001"
        assert data[0]["question"] == "What is the Holloway portfolio value?"

    async def test_limit_parameter_respected(self, async_client):
        import database
        for i in range(10):
            await database.save_query(
                request_id=f"lim-{i:03d}",
                session_id="s1",
                question=f"Question {i}",
                response=f"Answer {i}",
                total_latency_ms=500.0,
                retrieval_latency_ms=50.0,
                llm_latency_ms=450.0,
                chunks_retrieved=1,
                chunk_scores=[0.9],
                chunk_titles=["doc.pdf"],
                cache_hit=False,
                error=None,
                error_type=None,
                query_category="factual",
            )
        data = (await async_client.get("/observability/queries?limit=3")).json()
        assert len(data) == 3


# ── Latency Endpoint ──────────────────────────────────────────────────────────
class TestLatencyEndpoint:

    async def test_returns_200(self, async_client):
        assert (await async_client.get("/observability/latency")).status_code == 200

    async def test_returns_empty_list_on_empty_db(self, async_client):
        assert (await async_client.get("/observability/latency")).json() == []

    async def test_returns_latency_data_with_queries(self, async_client_with_data):
        data = (await async_client_with_data.get("/observability/latency")).json()
        assert len(data) == 1
        assert "total_latency_ms" in data[0]
        assert "retrieval_latency_ms" in data[0]
        assert "llm_latency_ms" in data[0]


# ── Slow Queries Endpoint ─────────────────────────────────────────────────────
class TestSlowQueriesEndpoint:

    async def test_returns_200(self, async_client):
        assert (await async_client.get("/observability/slow")).status_code == 200

    async def test_returns_empty_on_no_slow_queries(self, async_client_with_data):
        data = (await async_client_with_data.get("/observability/slow")).json()
        assert data == []


# ── Chunks Endpoint ───────────────────────────────────────────────────────────
class TestChunksEndpoint:

    async def test_returns_200(self, async_client):
        assert (await async_client.get("/observability/chunks")).status_code == 200

    async def test_returns_chunk_data(self, async_client_with_data):
        data = (await async_client_with_data.get("/observability/chunks")).json()
        docs = {item["document"] for item in data}
        assert "report.pdf" in docs
        assert "memo.pdf" in docs


# ── Feedback Endpoint ─────────────────────────────────────────────────────────
class TestFeedbackEndpoint:

    async def test_thumbs_up_saved(self, async_client_with_data):
        response = await async_client_with_data.post(
            "/observability/feedback/route-test-001",
            json={"feedback": "thumbs_up"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_thumbs_down_saved(self, async_client_with_data):
        response = await async_client_with_data.post(
            "/observability/feedback/route-test-001",
            json={"feedback": "thumbs_down"},
        )
        assert response.status_code == 200

    async def test_invalid_feedback_returns_400(self, async_client_with_data):
        response = await async_client_with_data.post(
            "/observability/feedback/route-test-001",
            json={"feedback": "meh"},
        )
        assert response.status_code == 400

    async def test_missing_query_returns_404(self, async_client):
        response = await async_client.post(
            "/observability/feedback/nonexistent-id",
            json={"feedback": "thumbs_up"},
        )
        assert response.status_code == 404


# ── Session Handling ──────────────────────────────────────────────────────────
class TestSessionHandling:

    def test_new_session_generates_uuid(self):
        """
        _get_or_create_session_id must return a new UUID and is_new=True
        when no session cookie is present.
        """
        from main import _get_or_create_session_id, SESSION_COOKIE_NAME
        from fastapi.testclient import TestClient
        from unittest.mock import MagicMock

        # Simulate a request with no session cookie
        mock_request = MagicMock()
        mock_request.cookies = {}

        session_id, is_new = _get_or_create_session_id(mock_request)
        assert is_new is True
        assert len(session_id) == 36  # UUID4 format
        assert session_id.count("-") == 4

    def test_existing_session_cookie_returned(self):
        """
        _get_or_create_session_id must return the existing cookie value
        and is_new=False when a session cookie is present.
        """
        from main import _get_or_create_session_id, SESSION_COOKIE_NAME
        from unittest.mock import MagicMock

        existing_id = "existing-session-abc-123"
        mock_request = MagicMock()
        mock_request.cookies = {SESSION_COOKIE_NAME: existing_id}

        session_id, is_new = _get_or_create_session_id(mock_request)
        assert is_new is False
        assert session_id == existing_id

    def test_two_new_sessions_get_different_ids(self):
        """Each new session must get a unique ID."""
        from main import _get_or_create_session_id
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.cookies = {}

        id1, _ = _get_or_create_session_id(mock_request)
        id2, _ = _get_or_create_session_id(mock_request)
        assert id1 != id2