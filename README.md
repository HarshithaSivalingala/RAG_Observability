# Verba Observability

A production-grade observability layer built on top of [Verba](https://github.com/weaviate/Verba), an open-source RAG application. The idea is simple: sit a FastAPI reverse proxy on port 8001 that intercepts every WebSocket and HTTP request before forwarding it to Verba on port 8000, recording latency, caching responses, and logging metadata at the transport layer without touching Verba's application code.

This project was built to demonstrate what production AI engineering actually looks like not just building a RAG chatbot, but operating one.

---

## What It Does

Every time someone asks a question in Verba, the proxy intercepts it, times it, categorizes it, saves it to a database, and optionally serves it from cache. A React dashboard polls the metrics API every 5 seconds and displays everything live.

The demo uses three fake internal financial documents, a client portfolio report, an investment strategy memo, and a quarterly audit report to simulate a real private financial firm use case where data can't be sent to external AI providers.

---

## Architecture

```
Browser → Proxy (port 8001) → Verba RAG (port 8000) → Weaviate + Ollama
                ↓
           SQLite DB
                ↓
       React Dashboard (port 5173)
```

The proxy is completely transparent to both the browser and Verba. Verba has no idea it's being intercepted.

---

## Metrics Tracked

**Latency**
- Total end-to-end latency per query
- p50 (median) - latency across all queries
- p95 latency - the number SLAs are written against
- Average latency over time

**Reliability**
- Error rate — percentage of queries that failed
- Empty response detection — queries where the model returned nothing
- Slow query flagging — anything over 10 seconds gets alerted separately

**Efficiency**
- Cache hit rate — percentage of queries served instantly from cache without hitting the model
- Per-document retrieval frequency — which documents get used most
- Response length tracking

**Quality**
- Thumbs up / thumbs down feedback per query — the only metric that tells you if the answer was actually correct, not just fast
- Query categorization — financial, compliance, analytical, factual, general

**Traceability**
- Full query history with timestamps, session IDs, and request IDs
- Expandable row detail showing full question, response preview, retrieved documents, and error details
- Sortable by newest, oldest, slowest, fastest

---

## What's On The Dashboard

The dashboard is styled in dark theme, monospace metrics, teal accents, dense information layout.

- **5 metric cards** — total queries, p50, p95, error rate, cache hit rate. Each card changes color based on thresholds (green → yellow → red as things get worse)
- **Latency chart** — area chart showing total and LLM latency over time. Slow queries appear as red dots
- **Slow query alerts panel** — dedicated panel showing every query that exceeded 10 seconds with the error message if there was one
- **Query history table** — full log of every question with timestamp, category badge, latency, chunk count, status, and thumbs up/down buttons. Click any row to expand the full detail view
- **Document usage chart** — horizontal bars showing which documents are retrieved most often with average similarity scores

---

## Tech Stack

**Backend**
- FastAPI + uvicorn for the proxy and metrics API
- SQLite + aiosqlite for async metric storage
- In-memory cache with SHA-256 keys and 5-minute TTL
- WebSocket bridging with AbortController-based cancellation
- pytest with 123 passing tests covering cache, database, adapter, HTTP helpers, API routes, and end-to-end WebSocket flow

**Frontend**
- React + Vite
- Recharts for the latency area chart
- CSS variables for theming
- JetBrains Mono + DM Sans fonts
- Single polling hook with proper cleanup and failure handling

**RAG Stack**
- Verba (Weaviate) for document storage and hybrid search
- nomic-embed-text via Ollama for embeddings
- llama3 via Ollama for generation
- Everything runs locally, no data leaves the machine

---

## Known Limitation

Retrieval latency shows as 0ms for all queries. This is because Verba streams LLM tokens directly without sending chunk data through the WebSocket, retrieval happens inside Verba's backend before streaming begins. Total latency is accurate. The retrieval/LLM breakdown requires inspecting Verba's internal WebSocket message format to extract the split point.

---

## Running It

You need four things running simultaneously:

```bash
1. Start Ollama
brew services start ollama

2. Start Verba
cd Verba && docker compose up -d

3. Start the proxy (from verba-observability/backend)
uvicorn main:app --port 8001 --reload

4. Start the dashboard (from verba-observability/frontend)
npm run dev
```

Use Verba at `http://localhost:8001` (through the proxy, not 8000 directly).
Dashboard is at `http://localhost:5173`.

Set `VITE_API_URL` in `.env.local` to point the dashboard at a different proxy URL for staging or production.

---

## Why This Project

Most AI portfolio projects stop at "I built a RAG chatbot." This one goes further and shows the operational side, the 70% of production AI work that nobody puts in their portfolio. Latency tracking, caching, error classification, slow query alerting, feedback collection, and a live dashboard are all standard requirements for any enterprise AI deployment. Building them from scratch on top of an existing system, without modifying the underlying RAG, demonstrates a different class of engineering than building the RAG itself.
