"""
test_websocket.py — Fixed for websockets 16.0.

Changes:
- Uses websockets.serve() instead of websockets.server.serve()
- Uses asyncio.timeout() for Python 3.11+ compatibility
- Mock Verba server uses the new connection handler signature
"""

import asyncio
import json
import pytest
import pytest_asyncio
import websockets
from websockets import serve


# ── Mock Verba WebSocket Server ───────────────────────────────────────────────
async def mock_verba_handler(websocket):
    """
    Simulates Verba's WebSocket behavior:
    1. Receives a question
    2. Sends back chunks (retrieval phase)
    3. Sends back LLM response tokens
    """
    async for message in websocket:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            continue

        question = (
            data.get("query")
            or data.get("message")
            or data.get("question")
            or ""
        )
        if not question:
            continue

        # Simulate retrieval phase
        await websocket.send(json.dumps({
            "chunks": [
                {"doc_name": "report.pdf", "score": 0.92},
                {"doc_name": "memo.pdf", "score": 0.85},
            ]
        }))
        await asyncio.sleep(0.01)

        # Simulate LLM streaming
        for token in ["The ", "portfolio ", "value ", "is ", "$4,820,350."]:
            await websocket.send(json.dumps({"message": token}))
            await asyncio.sleep(0.005)


@pytest_asyncio.fixture
async def mock_verba_port():
    """Start a mock Verba WebSocket server on a random port."""
    async with serve(mock_verba_handler, "localhost", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield port


@pytest_asyncio.fixture
async def proxy_port(mock_verba_port, tmp_path, monkeypatch):
    """
    Start the proxy pointed at the mock Verba server.
    Returns the proxy's port.
    """
    import database
    import main

    monkeypatch.setattr(main, "VERBA_URL", f"http://localhost:{mock_verba_port}")
    monkeypatch.setattr(main, "VERBA_WS_URL", f"ws://localhost:{mock_verba_port}")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "ws_test.db"))
    database._db = None

    import uvicorn
    config = uvicorn.Config(
        main.app,
        host="127.0.0.1",
        port=0,
        log_level="error",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    # Wait for startup
    for _ in range(50):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:
        raise RuntimeError("Proxy server failed to start")

    port = server.servers[0].sockets[0].getsockname()[1]
    yield port

    server.should_exit = True
    await asyncio.wait_for(task, timeout=5.0)


# ── Helpers ───────────────────────────────────────────────────────────────────
async def collect_messages(port: int, question: str, timeout: float = 5.0) -> list[dict]:
    """Connect to proxy, send question, collect all messages until close."""
    uri = f"ws://localhost:{port}/ws/generate_stream"
    messages = []
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"query": question}))
        try:
            async with asyncio.timeout(timeout):
                async for raw in ws:
                    try:
                        messages.append(json.loads(raw))
                    except json.JSONDecodeError:
                        pass
        except (
            asyncio.TimeoutError,
            websockets.exceptions.ConnectionClosedOK,
            websockets.exceptions.ConnectionClosedError,  # cache hit closes connection
        ):
            pass
    return messages


# ── Tests ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestWebSocketProxy:

    async def test_question_forwarded_to_verba(self, proxy_port):
        """Browser sends question → proxy forwards → response received."""
        messages = await collect_messages(proxy_port, "What is the portfolio value?")
        assert len(messages) > 0

    async def test_chunks_received_from_verba(self, proxy_port):
        """Chunks from mock Verba must be forwarded to browser unchanged."""
        messages = await collect_messages(proxy_port, "What is the value?")
        chunk_messages = [m for m in messages if "chunks" in m]
        assert len(chunk_messages) > 0
        chunks = chunk_messages[0]["chunks"]
        doc_names = [c.get("doc_name") for c in chunks]
        assert "report.pdf" in doc_names

    async def test_response_tokens_received(self, proxy_port):
        """LLM response tokens must be forwarded to browser."""
        messages = await collect_messages(proxy_port, "What is the value?")
        tokens = [
            m["message"] for m in messages
            if "message" in m and not m.get("cached")
        ]
        full_response = "".join(tokens)
        assert "$4,820,350" in full_response

    async def test_query_saved_to_database(self, proxy_port):
        """After a query completes, metrics must be saved to the database."""
        import database
        await collect_messages(proxy_port, "What is the portfolio value?")
        await asyncio.sleep(0.3)  # Give finally block time to save

        queries = await database.get_recent_queries()
        assert len(queries) >= 1
        assert queries[0]["question"] == "What is the portfolio value?"

    async def test_cache_hit_skips_verba(self, proxy_port):
        """Second identical query must be served from cache."""
        import database

        # First query — cache miss
        await collect_messages(proxy_port, "cache test question")
        await asyncio.sleep(0.2)

        # Second query — should hit cache
        messages = await collect_messages(proxy_port, "cache test question")
        cached_messages = [m for m in messages if m.get("cached") is True]
        assert len(cached_messages) >= 1, \
            "Expected at least one cached=True message on second query"

        await asyncio.sleep(0.2)
        queries = await database.get_recent_queries(limit=10)
        cache_hits = [q for q in queries if q["cache_hit"] == 1]
        assert len(cache_hits) >= 1

    async def test_disconnect_does_not_leave_dangling_tasks(self, proxy_port):
        """Disconnecting mid-stream must not break subsequent requests."""
        uri = f"ws://localhost:{proxy_port}/ws/generate_stream"

        # Connect, send, disconnect immediately
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"query": "disconnect test"}))
            await ws.close()

        await asyncio.sleep(0.3)

        # Proxy must still serve subsequent requests correctly
        messages = await collect_messages(proxy_port, "post-disconnect query")
        assert len(messages) > 0