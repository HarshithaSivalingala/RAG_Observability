"""
main.py — Reverse Proxy + Metrics API for Verba Observability

"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import websockets
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import (
    close_db,
    get_aggregated_metrics,
    get_chunk_usage,
    get_latency_over_time,
    get_recent_queries,
    get_slow_queries,
    init_db,
    save_feedback,
    save_query,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
VERBA_URL = "http://localhost:8000"
VERBA_WS_URL = "ws://localhost:8000"
PROXY_PORT = 8001
CACHE_TTL_SECONDS = 300
SLOW_QUERY_THRESHOLD_MS = 10_000
SESSION_COOKIE_NAME = "verba_obs_session"

HOP_BY_HOP_HEADERS = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
    "content-length", "host",
})


# ── Pure Helper Functions (testable without running the server) ───────────────
def _filter_headers(headers: dict) -> dict:
    """Remove hop-by-hop headers from a header dict."""
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}


def _build_proxy_url(path: str, query_params: dict) -> tuple[str, dict]:
    """
    Return (url, params_dict) for an httpx request.
    Using params= instead of manual string building avoids encoding bugs
    with special characters in query values.
    """
    url = f"{VERBA_URL}/{path}"
    return url, dict(query_params)


# ── Verba Message Adapter ─────────────────────────────────────────────────────
class VerbaMessageAdapter:
    """
    Single place that knows how to read and write Verba WebSocket messages.

    Why this exists:
    Without an adapter, message parsing is scattered across the proxy with
    hardcoded key names everywhere. If Verba changes its schema, we fix it
    in one place instead of hunting through the codebase.

    All methods are static — no state, fully testable.
    """

    # Keys Verba uses to send the user's question
    _QUESTION_KEYS = ("query", "message", "question", "input")

    # Keys Verba uses to send the LLM response token
    _RESPONSE_KEYS = ("message", "text", "content")

    # Keys Verba uses to send retrieved chunks
    _CHUNK_KEYS = ("chunks", "documents")

    # Keys Verba uses for document title within a chunk
    _TITLE_KEYS = ("doc_name", "title", "document", "name")

    @staticmethod
    def extract_question(data: dict) -> Optional[str]:
        """Extract the user's question from a browser→Verba message."""
        for key in VerbaMessageAdapter._QUESTION_KEYS:
            value = data.get(key)
            if value and isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def extract_chunks(data: dict) -> list[dict]:
        """
        Extract retrieved chunks from a Verba→browser message.
        Returns a list of dicts with 'title' and 'score' keys.
        """
        for key in VerbaMessageAdapter._CHUNK_KEYS:
            raw = data.get(key)
            if raw and isinstance(raw, list):
                result = []
                for chunk in raw:
                    if not isinstance(chunk, dict):
                        continue
                    title = next(
                        (chunk[k] for k in VerbaMessageAdapter._TITLE_KEYS if k in chunk),
                        "Unknown",
                    )
                    try:
                        score = float(chunk.get("score") or chunk.get("distance") or 0.0)
                    except (TypeError, ValueError):
                        score = 0.0
                    result.append({"title": str(title), "score": round(score, 4)})
                return result
        return []

    @staticmethod
    def extract_response_token(data: dict) -> Optional[str]:
        """Extract a response token from a Verba→browser message."""
        for key in VerbaMessageAdapter._RESPONSE_KEYS:
            value = data.get(key)
            if value and isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def format_cached_response(response: str) -> str:
        """
        Format a cached response using Verba's live response format.
        Uses the 'message' key since that is Verba's primary response field.
        The 'cached' flag lets the frontend optionally display a cache indicator.
        """
        return json.dumps({
            "message": response,
            "cached": True,
        })


# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict[str, dict] = {}


def _cache_key(question: str) -> str:
    """Stable SHA-256 cache key — identical across process restarts."""
    return hashlib.sha256(question.strip().lower().encode()).hexdigest()


def _get_from_cache(question: str) -> Optional[dict]:
    """Return cached entry if present and not expired."""
    key = _cache_key(question)
    entry = _cache.get(key)
    if not entry:
        return None
    if datetime.now(timezone.utc) > entry["expires_at"]:
        del _cache[key]
        logger.info("🗑️  Cache expired: '%s'", question[:60])
        return None
    logger.info("✅ Cache hit: '%s'", question[:60])
    return entry


def _save_to_cache(
    question: str,
    response: str,
    chunk_scores: list[float],
    chunk_titles: list[str],
) -> None:
    """Save response and its chunk metadata to cache."""
    _cache[_cache_key(question)] = {
        "response": response,
        "chunk_scores": chunk_scores,
        "chunk_titles": chunk_titles,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=CACHE_TTL_SECONDS),
    }
    logger.info("💾 Cached: '%s'", question[:60])


async def _cleanup_cache() -> None:
    """
    Background task — runs every 60 seconds.
    Proactively removes expired entries so memory never grows unbounded.
    """
    while True:
        await asyncio.sleep(60)
        now = datetime.now(timezone.utc)
        expired = [k for k, v in _cache.items() if now > v["expires_at"]]
        for key in expired:
            del _cache[key]
        if expired:
            logger.info("🧹 Cache cleanup: removed %d expired entries", len(expired))


# ── Query Categorization ──────────────────────────────────────────────────────
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "financial": [
        "portfolio", "investment", "return", "asset", "equity",
        "revenue", "profit", "loss", "dividend", "stock", "fund",
        "allocation", "value", "ytd", "performance", "holdings",
    ],
    "compliance": [
        "compliance", "regulation", "audit", "sec", "finra", "rule",
        "violation", "policy", "legal", "regulatory", "fiduciary",
        "deadline", "requirement",
    ],
    "analytical": [
        "compare", "difference", "versus", "vs", "better", "worse",
        "trend", "analysis", "breakdown", "why", "how", "explain",
    ],
    "factual": [
        "what is", "who is", "when", "where", "which",
        "how much", "how many", "what are", "list", "name", "define",
    ],
}


def categorize_query(question: str) -> str:
    q = question.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return category
    return "general"


def classify_error(error: str) -> str:
    e = error.lower()
    if "timeout" in e or "timed out" in e:
        return "timeout"
    if "connection" in e or "refused" in e:
        return "connection_error"
    if "empty" in e:
        return "empty_response"
    return "unknown"


# ── Session Tracking ──────────────────────────────────────────────────────────
def _get_or_create_session_id(request: Request) -> tuple[str, bool]:
    """
    Return (session_id, is_new).
    Reads from HttpOnly cookie for consistent cross-request tracking.
    Cookie-based sessions survive page refreshes and multiple tabs.
    """
    existing = request.cookies.get(SESSION_COOKIE_NAME)
    if existing:
        return existing, False
    return str(uuid.uuid4()), True


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Verba Observability Proxy on port %d", PROXY_PORT)
    await init_db()
    cleanup_task = asyncio.create_task(_cleanup_cache())
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await close_db()
    logger.info("👋 Proxy shutdown complete")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Verba Observability Proxy",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:8001",
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)


# ── WebSocket Proxy ───────────────────────────────────────────────────────────
@app.websocket("/ws/{path:path}")
async def websocket_proxy(websocket: WebSocket, path: str):
    """
    Intercept WebSocket chat queries.

    Session ID comes from cookie passed as query param since WebSocket
    upgrade requests cannot set cookies directly.
    """
    connection_id = str(uuid.uuid4())
    session_id = (
        websocket.cookies.get(SESSION_COOKIE_NAME)
        or websocket.query_params.get("session_id")
        or str(uuid.uuid4())[:16]
    )

    await websocket.accept()
    logger.info("🔌 WS connected [%s] session=%s", connection_id, session_id[:8])

    request_id: Optional[str] = None
    question = ""
    response_parts: list[str] = []
    chunk_scores: list[float] = []
    chunk_titles: list[str] = []
    chunks_retrieved = 0
    error: Optional[str] = None
    error_type: Optional[str] = None
    cache_hit = False

    total_start: Optional[float] = None
    retrieval_start: Optional[float] = None
    retrieval_end: Optional[float] = None
    llm_start: Optional[float] = None
    llm_end: Optional[float] = None

    def reset_query_state() -> None:
        nonlocal request_id, question, response_parts
        nonlocal chunk_scores, chunk_titles, chunks_retrieved
        nonlocal error, error_type, cache_hit
        nonlocal total_start, retrieval_start, retrieval_end, llm_start, llm_end

        request_id = None
        question = ""
        response_parts = []
        chunk_scores = []
        chunk_titles = []
        chunks_retrieved = 0
        error = None
        error_type = None
        cache_hit = False
        total_start = None
        retrieval_start = None
        retrieval_end = None
        llm_start = None
        llm_end = None

    def start_query(new_question: str) -> None:
        nonlocal request_id, question, total_start

        reset_query_state()
        request_id = str(uuid.uuid4())
        question = new_question
        total_start = time.monotonic()

    async def finalize_query() -> None:
        nonlocal request_id

        if not request_id or not question or total_start is None:
            return

        total_ms = (time.monotonic() - total_start) * 1000
        retrieval_ms = (
            (retrieval_end - retrieval_start) * 1000
            if retrieval_start and retrieval_end else 0.0
        )
        llm_ms = (
            (llm_end - llm_start) * 1000
            if llm_start and llm_end else 0.0
        )
        full_response = "".join(response_parts)
        category = categorize_query(question)

        if full_response and not error and not cache_hit:
            _save_to_cache(question, full_response, chunk_scores, chunk_titles)

        try:
            await save_query(
                request_id=request_id,
                session_id=session_id,
                question=question,
                response=full_response or None,
                total_latency_ms=total_ms,
                retrieval_latency_ms=retrieval_ms,
                llm_latency_ms=llm_ms,
                chunks_retrieved=chunks_retrieved,
                chunk_scores=chunk_scores,
                chunk_titles=chunk_titles,
                cache_hit=cache_hit,
                error=error,
                error_type=error_type,
                query_category=category,
            )
            logger.info(
                "✅ [%s] total=%.0fms retrieval=%.0fms llm=%.0fms cache=%s",
                request_id,
                total_ms,
                retrieval_ms,
                llm_ms,
                "hit" if cache_hit else "miss",
            )
        except Exception as db_err:
            logger.error("❌ DB save failed [%s]: %s", request_id, db_err)
        finally:
            reset_query_state()

    verba_ws_uri = f"{VERBA_WS_URL}/ws/{path}"

    try:
        async with websockets.connect(verba_ws_uri) as verba_ws:

            async def browser_to_verba():
                nonlocal retrieval_start, cache_hit
                nonlocal chunk_scores, chunk_titles, response_parts, llm_start, llm_end

                async for raw in websocket.iter_text():
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("⚠️ Non-JSON from browser [%s]", connection_id)
                        await verba_ws.send(raw)
                        continue

                    if not isinstance(data, dict):
                        logger.warning(
                            "⚠️ Unexpected type from browser [%s]: %s",
                            connection_id, type(data).__name__,
                        )
                        await verba_ws.send(raw)
                        continue

                    detected = VerbaMessageAdapter.extract_question(data)
                    if detected:
                        start_query(detected)
                        logger.info("❓ [%s]: '%s'", request_id, question[:80])

                        cached = _get_from_cache(question)
                        if cached:
                            cache_hit = True
                            chunk_scores = cached["chunk_scores"]
                            chunk_titles = cached["chunk_titles"]
                            response_parts = [cached["response"]]
                            llm_start = time.monotonic()
                            llm_end = llm_start
                            # Serve from cache — do NOT forward to Verba
                            await websocket.send_text(
                                VerbaMessageAdapter.format_cached_response(cached["response"])
                            )
                            logger.info("⚡ Served from cache [%s]", request_id)
                            await finalize_query()
                            continue

                    retrieval_start = time.monotonic()
                    await verba_ws.send(raw)

            async def verba_to_browser():
                nonlocal chunks_retrieved, chunk_scores, chunk_titles
                nonlocal retrieval_end, llm_start, llm_end, response_parts
                nonlocal error, error_type

                async for raw in verba_ws:
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        await websocket.send_text(raw)
                        continue

                    if not isinstance(data, dict):
                        await websocket.send_text(raw)
                        continue

                    # Log any keys we don't recognise helps detect schema changes
                    known = {
                        "chunks", "documents", "message", "text", "content",
                        "error", "status", "type", "cached", "finish_reason",
                        "full_text", "distance",
                    }
                    unknown = set(data.keys()) - known
                    if unknown:
                        logger.debug("ℹ️ Unknown Verba keys [%s]: %s", request_id or connection_id, unknown)

                    # Retrieval phase
                    extracted_chunks = VerbaMessageAdapter.extract_chunks(data)
                    if extracted_chunks:
                        chunks_retrieved = len(extracted_chunks)
                        chunk_scores = [c["score"] for c in extracted_chunks]
                        chunk_titles = [c["title"] for c in extracted_chunks]
                        retrieval_end = time.monotonic()
                        llm_start = time.monotonic()
                        logger.info("📄 %d chunks [%s]", chunks_retrieved, request_id)

                    # LLM response phase
                    token = VerbaMessageAdapter.extract_response_token(data)
                    if token:
                        response_parts.append(token)
                        llm_end = time.monotonic()

                    if data.get("error"):
                        error = str(data["error"])
                        error_type = classify_error(error)
                        logger.error("❌ Verba error [%s]: %s", request_id or connection_id, error)

                    await websocket.send_text(raw)

                    if data.get("finish_reason") == "stop":
                        await finalize_query()

            browser_task = asyncio.create_task(browser_to_verba())
            verba_task = asyncio.create_task(verba_to_browser())

            try:
                done, pending = await asyncio.wait(
                    [browser_task, verba_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
                for task in done:
                    exc = task.exception()
                    if exc:
                        raise exc
            except Exception:
                browser_task.cancel()
                verba_task.cancel()
                raise

    except WebSocketDisconnect:
        logger.info("🔌 Disconnected [%s]", request_id or connection_id)
    except websockets.exceptions.ConnectionClosedError as e:
        error = f"Verba WS closed: {e}"
        error_type = "connection_error"
        logger.error("❌ [%s] %s", request_id or connection_id, error)
    except Exception as e:
        error = str(e)
        error_type = classify_error(error)
        logger.error("❌ WS error [%s]: %s", request_id or connection_id, error)
    finally:
        await finalize_query()


# ── Metrics API ───────────────────────────────────────────────────────────────
# IMPORTANT: These routes must be registered BEFORE the catch-all /{path:path}
# route below. FastAPI matches routes in registration order — if the catch-all
# is registered first it will intercept all /observability/* requests.

@app.get("/observability/health")
async def health():
    return JSONResponse(content={
        "status": "healthy",
        "proxy_target": VERBA_URL,
        "cache_entries": len(_cache),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/observability/metrics")
async def metrics_summary():
    return JSONResponse(content=await get_aggregated_metrics())


@app.get("/observability/queries")
async def query_history(limit: int = 50):
    return JSONResponse(content=await get_recent_queries(limit=limit))


@app.get("/observability/latency")
async def latency_chart():
    return JSONResponse(content=await get_latency_over_time())


@app.get("/observability/slow")
async def slow_queries():
    return JSONResponse(content=await get_slow_queries())


@app.get("/observability/chunks")
async def chunk_usage():
    return JSONResponse(content=await get_chunk_usage())


@app.post("/observability/feedback/{request_id}")
async def submit_feedback(request_id: str, request: Request):
    try:
        body = await request.json()
        feedback = body.get("feedback")
        if feedback not in ("thumbs_up", "thumbs_down"):
            return JSONResponse(
                status_code=400,
                content={"error": "feedback must be thumbs_up or thumbs_down"},
            )
        updated = await save_feedback(request_id, feedback)
        if not updated:
            return JSONResponse(
                status_code=404,
                content={"error": f"Query {request_id} not found"},
            )
        return JSONResponse(content={"success": True, "request_id": request_id})
    except Exception as e:
        logger.error("❌ Feedback error [%s]: %s", request_id, str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── HTTP Proxy ────────────────────────────────────────────────────────────────
# Catch-all — must be registered LAST so observability routes match first
@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def http_proxy(request: Request, path: str):
    """
    Forward HTTP requests to Verba.
    - Filters hop-by-hop headers
    - Uses params= dict instead of manual query string
    - Sets session cookie on response if new session
    """
    session_id, is_new_session = _get_or_create_session_id(request)
    url, params = _build_proxy_url(path, dict(request.query_params))
    filtered_headers = _filter_headers(dict(request.headers))

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            proxied = await client.request(
                method=request.method,
                url=url,
                headers=filtered_headers,
                params=params,
                content=await request.body(),
            )
            response_headers = _filter_headers(dict(proxied.headers))
            response = Response(
                content=proxied.content,
                status_code=proxied.status_code,
                headers=response_headers,
            )
            if is_new_session:
                response.set_cookie(
                    key=SESSION_COOKIE_NAME,
                    value=session_id,
                    httponly=True,
                    samesite="lax",
                )
            return response

    except httpx.ConnectError:
        logger.error("❌ Cannot connect to Verba at %s", VERBA_URL)
        return JSONResponse(
            status_code=503,
            content={"error": "Verba is not reachable. Make sure it is running on port 8000."},
        )
    except httpx.TimeoutException:
        logger.error("❌ Verba request timed out: %s", url)
        return JSONResponse(
            status_code=504,
            content={"error": "Request to Verba timed out."},
        )
