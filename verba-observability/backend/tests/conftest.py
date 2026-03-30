"""
conftest.py — Shared pytest fixtures for all test modules.

Fixtures here are automatically available to every test file
without importing them explicitly.
"""

import asyncio
import pytest
import pytest_asyncio
import aiosqlite
from pathlib import Path


# ── Event Loop ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """Single event loop shared across the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Temporary Database ────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    """
    Provide a fresh initialized database for each test.
    Uses a temp file so tests never interfere with each other.
    Automatically closes after each test.
    """
    import database
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database._db = None
    await database.init_db()
    yield
    await database.close_db()


# ── Sample Query Data ─────────────────────────────────────────────────────────
@pytest.fixture
def sample_query():
    """Reusable sample query kwargs for save_query calls."""
    return dict(
        request_id="test-001",
        session_id="session-abc",
        question="What is the portfolio value?",
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


# ── Clean Cache ───────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the in-memory cache before every test automatically."""
    try:
        from main import _cache
        _cache.clear()
        yield
        _cache.clear()
    except ImportError:
        yield