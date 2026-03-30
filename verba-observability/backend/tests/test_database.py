"""
test_database.py — Tests for all database operations.

Covers:
- Table creation and schema
- save_query and get_recent_queries
- Chunk usage per-document accuracy
- p50/p95 percentile calculation
- Feedback save and retrieval
- Slow query flagging
- Aggregated metrics
"""

import pytest
import pytest_asyncio


@pytest.mark.asyncio
class TestDatabaseInit:

    async def test_creates_queries_table(self, db, tmp_path):
        import aiosqlite
        import database
        async with aiosqlite.connect(database.DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in await cursor.fetchall()}
        assert "queries" in tables

    async def test_creates_chunk_usage_table(self, db, tmp_path):
        import aiosqlite
        import database
        async with aiosqlite.connect(database.DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in await cursor.fetchall()}
        assert "chunk_usage" in tables

    async def test_does_not_create_aggregated_metrics_table(self, db, tmp_path):
        """This table was removed in v3 — must not exist."""
        import aiosqlite
        import database
        async with aiosqlite.connect(database.DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in await cursor.fetchall()}
        assert "aggregated_metrics" not in tables

    async def test_indexes_are_created(self, db, tmp_path):
        import aiosqlite
        import database
        async with aiosqlite.connect(database.DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
            indexes = {row[0] for row in await cursor.fetchall()}
        assert "idx_queries_timestamp" in indexes
        assert "idx_queries_session_id" in indexes
        assert "idx_queries_is_slow" in indexes
        assert "idx_chunk_usage_document" in indexes


@pytest.mark.asyncio
class TestSaveAndRetrieveQuery:

    async def test_save_and_retrieve(self, db, sample_query):
        from database import get_recent_queries, save_query
        await save_query(**sample_query)
        queries = await get_recent_queries(limit=10)
        assert len(queries) == 1
        q = queries[0]
        assert q["id"] == "test-001"
        assert q["question"] == "What is the portfolio value?"
        assert q["total_latency_ms"] == 1200.5
        assert q["query_category"] == "financial"

    async def test_chunk_scores_deserialized_as_list(self, db, sample_query):
        from database import get_recent_queries, save_query
        await save_query(**sample_query)
        queries = await get_recent_queries()
        assert queries[0]["chunk_scores"] == [0.92, 0.87]

    async def test_chunk_titles_deserialized_as_list(self, db, sample_query):
        from database import get_recent_queries, save_query
        await save_query(**sample_query)
        queries = await get_recent_queries()
        assert queries[0]["chunk_titles"] == ["report.pdf", "memo.pdf"]

    async def test_limit_respected(self, db, sample_query):
        from database import get_recent_queries, save_query
        for i in range(5):
            q = {**sample_query, "request_id": f"test-{i:03d}"}
            await save_query(**q)
        queries = await get_recent_queries(limit=3)
        assert len(queries) == 3

    async def test_ordered_newest_first(self, db, sample_query):
        from database import get_recent_queries, save_query
        for i in range(3):
            q = {**sample_query, "request_id": f"test-{i:03d}", "question": f"Q{i}"}
            await save_query(**q)
        queries = await get_recent_queries()
        # Most recent inserted last → should appear first
        assert queries[0]["question"] == "Q2"


@pytest.mark.asyncio
class TestChunkUsageAccuracy:
    """
    Chunk usage must count per individual document, not per JSON array.
    This was the main correctness bug in earlier versions.
    """

    async def test_individual_document_counts(self, db, sample_query):
        from database import get_chunk_usage, save_query

        # Query 1: uses report.pdf and memo.pdf
        await save_query(**{**sample_query, "request_id": "q1"})

        # Query 2: uses report.pdf only
        await save_query(**{
            **sample_query,
            "request_id": "q2",
            "chunk_titles": ["report.pdf"],
            "chunk_scores": [0.95],
            "chunks_retrieved": 1,
        })

        usage = await get_chunk_usage()
        usage_dict = {item["document"]: item["retrieval_count"] for item in usage}

        assert usage_dict["report.pdf"] == 2
        assert usage_dict["memo.pdf"] == 1

    async def test_avg_score_calculated_correctly(self, db, sample_query):
        from database import get_chunk_usage, save_query

        # Two queries both using report.pdf with scores 0.9 and 0.8
        await save_query(**{
            **sample_query,
            "request_id": "q1",
            "chunk_titles": ["report.pdf"],
            "chunk_scores": [0.9],
        })
        await save_query(**{
            **sample_query,
            "request_id": "q2",
            "chunk_titles": ["report.pdf"],
            "chunk_scores": [0.8],
        })

        usage = await get_chunk_usage()
        report = next(u for u in usage if u["document"] == "report.pdf")
        assert abs(report["avg_score"] - 0.85) < 0.001


@pytest.mark.asyncio
class TestPercentileCalculation:

    async def test_p95_uses_interpolation(self, db, sample_query):
        """p95 of [100..1000] with linear interpolation = 955.0"""
        from database import get_aggregated_metrics, save_query

        latencies = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
        for i, lat in enumerate(latencies):
            await save_query(**{
                **sample_query,
                "request_id": f"perc-{i:03d}",
                "total_latency_ms": float(lat),
                "llm_latency_ms": float(lat - 10),
            })

        metrics = await get_aggregated_metrics()
        assert abs(metrics["p95_latency_ms"] - 955.0) < 1.0

    async def test_p50_uses_interpolation(self, db, sample_query):
        """p50 of [100..1000] = 550.0"""
        from database import get_aggregated_metrics, save_query

        latencies = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
        for i, lat in enumerate(latencies):
            await save_query(**{
                **sample_query,
                "request_id": f"p50-{i:03d}",
                "total_latency_ms": float(lat),
                "llm_latency_ms": float(lat - 10),
            })

        metrics = await get_aggregated_metrics()
        assert abs(metrics["p50_latency_ms"] - 550.0) < 1.0

    async def test_percentile_with_single_value(self, db, sample_query):
        from database import get_aggregated_metrics, save_query
        await save_query(**{**sample_query, "total_latency_ms": 500.0})
        metrics = await get_aggregated_metrics()
        assert metrics["p95_latency_ms"] == 500.0
        assert metrics["p50_latency_ms"] == 500.0

    async def test_percentile_with_empty_db(self, db):
        from database import get_aggregated_metrics
        metrics = await get_aggregated_metrics()
        assert metrics["p95_latency_ms"] == 0.0
        assert metrics["p50_latency_ms"] == 0.0


@pytest.mark.asyncio
class TestFeedback:

    async def test_save_thumbs_up(self, db, sample_query):
        from database import get_recent_queries, save_feedback, save_query
        await save_query(**sample_query)
        updated = await save_feedback("test-001", "thumbs_up")
        assert updated is True
        queries = await get_recent_queries()
        assert queries[0]["feedback"] == "thumbs_up"

    async def test_save_thumbs_down(self, db, sample_query):
        from database import get_recent_queries, save_feedback, save_query
        await save_query(**sample_query)
        await save_feedback("test-001", "thumbs_down")
        queries = await get_recent_queries()
        assert queries[0]["feedback"] == "thumbs_down"

    async def test_returns_false_for_missing_query(self, db):
        from database import save_feedback
        result = await save_feedback("nonexistent-id", "thumbs_up")
        assert result is False

    async def test_invalid_feedback_raises(self, db):
        from database import save_feedback
        with pytest.raises(ValueError):
            await save_feedback("any-id", "invalid_value")


@pytest.mark.asyncio
class TestSlowQueryFlagging:

    async def test_slow_query_flagged(self, db, sample_query):
        from database import get_slow_queries, save_query
        await save_query(**{
            **sample_query,
            "request_id": "slow-001",
            "total_latency_ms": 15000.0,
        })
        slow = await get_slow_queries()
        assert len(slow) == 1
        assert slow[0]["id"] == "slow-001"

    async def test_fast_query_not_flagged(self, db, sample_query):
        from database import get_slow_queries, save_query
        await save_query(**{
            **sample_query,
            "total_latency_ms": 500.0,
        })
        slow = await get_slow_queries()
        assert len(slow) == 0

    async def test_slow_queries_ordered_by_latency_desc(self, db, sample_query):
        from database import get_slow_queries, save_query
        for i, lat in enumerate([12000, 20000, 15000]):
            await save_query(**{
                **sample_query,
                "request_id": f"slow-{i}",
                "total_latency_ms": float(lat),
            })
        slow = await get_slow_queries()
        latencies = [s["total_latency_ms"] for s in slow]
        assert latencies == sorted(latencies, reverse=True)


@pytest.mark.asyncio
class TestAggregatedMetrics:

    async def test_total_queries_count(self, db, sample_query):
        from database import get_aggregated_metrics, save_query
        for i in range(3):
            await save_query(**{**sample_query, "request_id": f"m-{i}"})
        metrics = await get_aggregated_metrics()
        assert metrics["total_queries"] == 3

    async def test_error_rate_calculation(self, db, sample_query):
        from database import get_aggregated_metrics, save_query
        # 1 success + 1 error = 50% error rate
        await save_query(**{**sample_query, "request_id": "ok-1"})
        await save_query(**{
            **sample_query,
            "request_id": "err-1",
            "error": "timeout",
            "error_type": "timeout",
        })
        metrics = await get_aggregated_metrics()
        assert metrics["error_rate"] == 50.0

    async def test_cache_hit_rate_calculation(self, db, sample_query):
        from database import get_aggregated_metrics, save_query
        await save_query(**{**sample_query, "request_id": "miss-1", "cache_hit": False})
        await save_query(**{**sample_query, "request_id": "hit-1", "cache_hit": True})
        metrics = await get_aggregated_metrics()
        assert metrics["cache_hit_rate"] == 50.0

    async def test_empty_db_returns_zeros(self, db):
        from database import get_aggregated_metrics
        metrics = await get_aggregated_metrics()
        assert metrics["total_queries"] == 0
        assert metrics["avg_latency_ms"] == 0.0
        assert metrics["error_rate"] == 0.0
