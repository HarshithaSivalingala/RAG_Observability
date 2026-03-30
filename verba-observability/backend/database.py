"""
database.py — SQLite database layer for Verba Observability

Changes from v2:
- Verified shared connection — single aiosqlite.Connection reused everywhere
- Added indexes on timestamp, session_id, is_slow_query for fast dashboard reads
- chunk_usage table stores one row per document — counts are always accurate
- Removed aggregated_metrics table entirely
- WAL mode enabled for better concurrent read performance
- Proper percentile interpolation for p50/p95
"""

import json
import logging
import aiosqlite
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "observability.db"
SLOW_QUERY_THRESHOLD_MS = 10_000

# Single shared connection — opened once in init_db(), reused everywhere
_db: Optional[aiosqlite.Connection] = None


# ── Schema ────────────────────────────────────────────────────────────────────
CREATE_QUERIES_TABLE = """
CREATE TABLE IF NOT EXISTS queries (
    id                   TEXT PRIMARY KEY,
    timestamp            TEXT NOT NULL,
    session_id           TEXT,
    question             TEXT NOT NULL,
    response             TEXT,
    query_category       TEXT,
    total_latency_ms     REAL,
    retrieval_latency_ms REAL,
    llm_latency_ms       REAL,
    chunks_retrieved     INTEGER DEFAULT 0,
    chunk_scores         TEXT,
    chunk_titles         TEXT,
    is_slow_query        INTEGER DEFAULT 0,
    cache_hit            INTEGER DEFAULT 0,
    error                TEXT,
    error_type           TEXT,
    feedback             TEXT,
    response_length      INTEGER DEFAULT 0,
    is_empty_response    INTEGER DEFAULT 0
);
"""

# One row per document per query — never group JSON arrays
CREATE_CHUNK_USAGE_TABLE = """
CREATE TABLE IF NOT EXISTS chunk_usage (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id   TEXT NOT NULL,
    document     TEXT NOT NULL,
    score        REAL DEFAULT 0.0,
    timestamp    TEXT NOT NULL,
    FOREIGN KEY (request_id) REFERENCES queries(id)
);
"""

# Indexes for the fields most commonly used in WHERE and ORDER BY
# Without indexes, every dashboard read does a full table scan
CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_queries_timestamp    ON queries(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_queries_session_id   ON queries(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_queries_is_slow      ON queries(is_slow_query);",
    "CREATE INDEX IF NOT EXISTS idx_queries_cache_hit    ON queries(cache_hit);",
    "CREATE INDEX IF NOT EXISTS idx_chunk_usage_document ON chunk_usage(document);",
    "CREATE INDEX IF NOT EXISTS idx_chunk_usage_request  ON chunk_usage(request_id);",
]


# ── Initialization ────────────────────────────────────────────────────────────
async def init_db() -> None:
    """
    Open a single shared database connection and create schema.

    Why shared connection:
    Opening a new SQLite connection for every operation adds ~1-2ms overhead
    per query. Under load (e.g. 10 concurrent dashboard polls) this adds up.
    A single shared async connection serves all operations without blocking
    because aiosqlite runs SQLite in a thread pool internally.

    WAL (Write-Ahead Logging) mode allows reads and writes to happen
    concurrently without blocking each other — important when the dashboard
    is polling while new queries are being saved.
    """
    global _db
    try:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row

        # WAL mode — better concurrent read/write performance
        await _db.execute("PRAGMA journal_mode=WAL;")
        # Faster writes — acceptable risk for observability data
        await _db.execute("PRAGMA synchronous=NORMAL;")

        await _db.execute(CREATE_QUERIES_TABLE)
        await _db.execute(CREATE_CHUNK_USAGE_TABLE)

        for index_sql in CREATE_INDEXES:
            await _db.execute(index_sql)

        await _db.commit()
        logger.info("✅ Database initialized at %s", DB_PATH)
    except Exception as e:
        logger.error("❌ Failed to initialize database: %s", str(e))
        raise


async def close_db() -> None:
    """Close the shared connection on shutdown."""
    global _db
    if _db:
        await _db.close()
        _db = None
        logger.info("👋 Database connection closed")


def _get_db() -> aiosqlite.Connection:
    """Return the shared connection. Raises clearly if init_db() was not called."""
    if _db is None:
        raise RuntimeError(
            "Database not initialized. Ensure init_db() is called at startup."
        )
    return _db


# ── Percentile ────────────────────────────────────────────────────────────────
def _percentile(sorted_values: list[float], p: float) -> float:
    """
    Linear interpolation percentile — same method as numpy.percentile.

    For p=95, n=10 values [100,200,...,1000]:
      index = 0.95 * (10-1) = 8.55
      floor=8 → 900, ceil=9 → 1000
      result = 900 + 0.55 * (1000 - 900) = 955.0
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (p / 100.0) * (len(sorted_values) - 1)
    floor_idx = int(index)
    ceil_idx = min(floor_idx + 1, len(sorted_values) - 1)
    fraction = index - floor_idx
    return sorted_values[floor_idx] + fraction * (
        sorted_values[ceil_idx] - sorted_values[floor_idx]
    )


# ── Write Operations ──────────────────────────────────────────────────────────
async def save_query(
    request_id: str,
    session_id: str,
    question: str,
    response: Optional[str],
    total_latency_ms: float,
    retrieval_latency_ms: float,
    llm_latency_ms: float,
    chunks_retrieved: int,
    chunk_scores: list[float],
    chunk_titles: list[str],
    cache_hit: bool,
    error: Optional[str],
    error_type: Optional[str],
    query_category: str,
) -> None:
    """
    Save a query and its metrics using the shared connection.
    Also inserts one row per retrieved document into chunk_usage
    so per-document counts are always accurate.
    """
    is_slow = total_latency_ms > SLOW_QUERY_THRESHOLD_MS
    is_empty = not response or len(response.strip()) == 0
    response_length = len(response) if response else 0

    if is_slow:
        logger.warning(
            "🐢 Slow query [%s]: %.0fms — '%s'",
            request_id, total_latency_ms, question[:80],
        )

    db = _get_db()
    try:
        await db.execute(
            """
            INSERT INTO queries (
                id, timestamp, session_id, question, response,
                query_category, total_latency_ms, retrieval_latency_ms,
                llm_latency_ms, chunks_retrieved, chunk_scores, chunk_titles,
                is_slow_query, cache_hit, error, error_type,
                response_length, is_empty_response
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?
            )
            """,
            (
                request_id,
                datetime.utcnow().isoformat(),
                session_id,
                question,
                response,
                query_category,
                total_latency_ms,
                retrieval_latency_ms,
                llm_latency_ms,
                chunks_retrieved,
                json.dumps(chunk_scores),
                json.dumps(chunk_titles),
                1 if is_slow else 0,
                1 if cache_hit else 0,
                error,
                error_type,
                response_length,
                1 if is_empty else 0,
            ),
        )

        # Insert one row per document into chunk_usage
        # This is the correct way to count per-document usage —
        # grouping JSON arrays in SQL gives wrong counts
        timestamp = datetime.utcnow().isoformat()
        for title, score in zip(chunk_titles, chunk_scores):
            await db.execute(
                """
                INSERT INTO chunk_usage (request_id, document, score, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (request_id, title, float(score), timestamp),
            )

        await db.commit()
        logger.info("💾 Saved [%s] %.0fms", request_id, total_latency_ms)

    except Exception as e:
        logger.error("❌ Failed to save query [%s]: %s", request_id, str(e))
        try:
            await db.rollback()
        except Exception:
            pass
        raise


async def save_feedback(request_id: str, feedback: str) -> bool:
    """Save thumbs up/down. Returns True if query was found and updated."""
    if feedback not in ("thumbs_up", "thumbs_down"):
        raise ValueError(f"Invalid feedback value: {feedback!r}")
    db = _get_db()
    try:
        cursor = await db.execute(
            "UPDATE queries SET feedback = ? WHERE id = ?",
            (feedback, request_id),
        )
        await db.commit()
        updated = cursor.rowcount > 0
        if not updated:
            logger.warning("⚠️ Feedback: query [%s] not found", request_id)
        return updated
    except Exception as e:
        logger.error("❌ Failed to save feedback [%s]: %s", request_id, str(e))
        raise


# ── Read Operations ───────────────────────────────────────────────────────────
async def get_recent_queries(limit: int = 50) -> list[dict]:
    """Most recent queries for the dashboard history table."""
    db = _get_db()
    try:
        cursor = await db.execute(
            """
            SELECT id, timestamp, session_id, question, response,
                   query_category, total_latency_ms, retrieval_latency_ms,
                   llm_latency_ms, chunks_retrieved, chunk_scores, chunk_titles,
                   is_slow_query, cache_hit, error, error_type,
                   feedback, response_length, is_empty_response
            FROM queries
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            row_dict = dict(row)
            row_dict["chunk_scores"] = json.loads(row_dict["chunk_scores"] or "[]")
            row_dict["chunk_titles"] = json.loads(row_dict["chunk_titles"] or "[]")
            result.append(row_dict)
        return result
    except Exception as e:
        logger.error("❌ Failed to fetch recent queries: %s", str(e))
        raise


async def get_aggregated_metrics() -> dict:
    """
    Compute metrics across all queries.
    p50/p95 use proper linear interpolation.
    """
    db = _get_db()
    try:
        cursor = await db.execute(
            """
            SELECT
                COUNT(*)                                                AS total_queries,
                AVG(total_latency_ms)                                   AS avg_latency_ms,
                AVG(CASE WHEN error IS NOT NULL THEN 1.0 ELSE 0.0 END)  AS error_rate,
                AVG(CASE WHEN cache_hit = 1    THEN 1.0 ELSE 0.0 END)  AS cache_hit_rate,
                SUM(is_slow_query)                                      AS slow_query_count,
                SUM(is_empty_response)                                  AS empty_response_count
            FROM queries
            """
        )
        row = dict(await cursor.fetchone())

        cursor = await db.execute(
            "SELECT total_latency_ms FROM queries ORDER BY total_latency_ms ASC"
        )
        latencies = [r[0] for r in await cursor.fetchall() if r[0] is not None]

        return {
            "total_queries":       row["total_queries"] or 0,
            "avg_latency_ms":      round(row["avg_latency_ms"] or 0, 2),
            "p50_latency_ms":      round(_percentile(latencies, 50), 2),
            "p95_latency_ms":      round(_percentile(latencies, 95), 2),
            "error_rate":          round((row["error_rate"] or 0) * 100, 2),
            "cache_hit_rate":      round((row["cache_hit_rate"] or 0) * 100, 2),
            "slow_query_count":    row["slow_query_count"] or 0,
            "empty_response_count": row["empty_response_count"] or 0,
        }
    except Exception as e:
        logger.error("❌ Failed to compute aggregated metrics: %s", str(e))
        raise


async def get_latency_over_time() -> list[dict]:
    """Per-query latency for the latency chart."""
    db = _get_db()
    try:
        cursor = await db.execute(
            """
            SELECT timestamp, total_latency_ms, retrieval_latency_ms,
                   llm_latency_ms, is_slow_query
            FROM queries
            ORDER BY timestamp ASC
            LIMIT 200
            """
        )
        return [dict(row) for row in await cursor.fetchall()]
    except Exception as e:
        logger.error("❌ Failed to fetch latency over time: %s", str(e))
        raise


async def get_slow_queries() -> list[dict]:
    """Queries that exceeded SLOW_QUERY_THRESHOLD_MS."""
    db = _get_db()
    try:
        cursor = await db.execute(
            """
            SELECT id, timestamp, question, total_latency_ms, error
            FROM queries
            WHERE is_slow_query = 1
            ORDER BY total_latency_ms DESC
            LIMIT 20
            """
        )
        return [dict(row) for row in await cursor.fetchall()]
    except Exception as e:
        logger.error("❌ Failed to fetch slow queries: %s", str(e))
        raise


async def get_chunk_usage() -> list[dict]:
    """
    Per-document retrieval frequency.
    Counts from chunk_usage table — one row per document per query —
    so counts are always correct and never affected by JSON grouping.
    """
    db = _get_db()
    try:
        cursor = await db.execute(
            """
            SELECT
                document,
                COUNT(*)   AS retrieval_count,
                AVG(score) AS avg_score
            FROM chunk_usage
            GROUP BY document
            ORDER BY retrieval_count DESC
            LIMIT 20
            """
        )
        return [
            {
                "document":        row["document"],
                "retrieval_count": row["retrieval_count"],
                "avg_score":       round(row["avg_score"] or 0.0, 4),
            }
            for row in await cursor.fetchall()
        ]
    except Exception as e:
        logger.error("❌ Failed to fetch chunk usage: %s", str(e))
        raise

