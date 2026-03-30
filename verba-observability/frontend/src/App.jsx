import { useState, useEffect, useRef, useCallback } from 'react'
import './index.css'
import MetricCards from './components/MetricCards'
import LatencyChart from './components/LatencyChart'
import QueryTable from './components/QueryTable'
import DocumentUsage from './components/DocumentUsage'
import SlowAlerts from './components/SlowAlerts'

// ── Config ────────────────────────────────────────────────────────────────────
// Use VITE_API_URL env variable so staging/prod don't require code changes.
// Set in .env.local: VITE_API_URL=https://your-proxy.example.com/observability
const API = import.meta.env.VITE_API_URL || 'http://localhost:8001/observability'
const POLL_INTERVAL = 5000
const MAX_FAILURES = 3

// ── Single polling hook ───────────────────────────────────────────────────────
// Fetches all endpoints in one loop so the UI refreshes simultaneously.
// Uses AbortController to cancel in-flight requests before issuing new ones,
// preventing stale responses from overwriting fresher data.
// Stops polling after MAX_FAILURES consecutive failures to avoid log spam.
function useObservabilityData() {
  const [data, setData] = useState({
    metrics: null,
    queries: null,
    latency: null,
    chunks: null,
    slow: null,
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [failureCount, setFailureCount] = useState(0)
  const abortRef = useRef(null)
  const failureCountRef = useRef(0)

  const poll = useCallback(async () => {
    // Cancel any in-flight request from the previous poll cycle
    if (abortRef.current) {
      abortRef.current.abort()
    }
    const controller = new AbortController()
    abortRef.current = controller
    const { signal } = controller

    const endpoints = [
      ['metrics',  `${API}/metrics`],
      ['queries',  `${API}/queries?limit=50`],
      ['latency',  `${API}/latency`],
      ['chunks',   `${API}/chunks`],
      ['slow',     `${API}/slow`],
    ]

    try {
      const results = await Promise.all(
        endpoints.map(async ([key, url]) => {
          const res = await fetch(url, { signal })
          if (!res.ok) throw new Error(`${key}: HTTP ${res.status}`)
          return [key, await res.json()]
        })
      )

      if (signal.aborted) return  // A newer poll started — discard results

      const next = Object.fromEntries(results)
      setData(next)
      setError(null)
      setLoading(false)
      setFailureCount(0)
      // lastUpdated tied to actual successful refreshes — not a separate timer
      setLastUpdated(new Date())
    } catch (e) {
      if (e.name === 'AbortError') return  // Intentional cancel — not a failure

      setFailureCount(f => f + 1)
      failureCountRef.current += 1
      setError(e.message)
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    poll()

    const id = setInterval(() => {
      // Stop polling after MAX_FAILURES consecutive failures
      if (failureCountRef.current >= MAX_FAILURES) {
        clearInterval(id)
        setError(`Polling stopped after ${MAX_FAILURES} failures. Is the proxy running?`)
        return
      }
      poll()
    }, POLL_INTERVAL)

    return () => {
      clearInterval(id)
      if (abortRef.current) abortRef.current.abort()
    }
  }, [poll])

  return { data, loading, error, lastUpdated }
}

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const { data, loading, error, lastUpdated } = useObservabilityData()

  const handleFeedback = async (requestId, feedback) => {
    // Returns { ok, error } so callers can show failure state
    try {
      const res = await fetch(`${API}/feedback/${requestId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        return { ok: false, error: body.error || `HTTP ${res.status}` }
      }
      return { ok: true }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  }

  return (
    <div style={s.app}>
      {/* ── Header ── */}
      <header style={s.header}>
        <div style={s.headerLeft}>
          <div style={s.logo}>
            <span style={s.logoIcon}>◈</span>
            <span style={s.logoText}>Verba Observability</span>
          </div>
          <div style={s.badge}>
            <span style={{ ...s.dot, animation: error ? 'none' : 'pulse 2s infinite', background: error ? 'var(--red)' : 'var(--green)' }} />
            {error ? 'Disconnected' : 'Live'}
          </div>
        </div>
        <div style={s.headerRight}>
          <span style={s.updated}>
            {lastUpdated
              ? `Updated ${lastUpdated.toLocaleTimeString()}`
              : loading ? 'Connecting…' : 'Waiting…'}
          </span>
          <div style={s.pill}>RAG Monitor</div>
        </div>
      </header>

      {/* ── Error Banner ── */}
      {error && (
        <div style={s.errorBanner} role="alert">
          <span style={s.errorIcon}>⚠</span>
          <span>{error}</span>
          <span style={s.errorHint}>Check that the proxy is running on port 8001</span>
        </div>
      )}

      {/* ── Main ── */}
      <main style={s.main}>
        <MetricCards metrics={data.metrics} loading={loading} />

        <div className="two-col">
          <div className="main-col">
            <LatencyChart data={data.latency} loading={loading} />
          </div>
          <div className="side-col">
            <SlowAlerts queries={data.slow} loading={loading} />
          </div>
        </div>

        <div className="two-col">
          <div className="main-col">
            <QueryTable
              queries={data.queries}
              loading={loading}
              onFeedback={handleFeedback}
            />
          </div>
          <div className="side-col">
            <DocumentUsage chunks={data.chunks} loading={loading} />
          </div>
        </div>
      </main>
    </div>
  )
}

const s = {
  app: {
    minHeight: '100vh',
    background: 'var(--bg-base)',
    display: 'flex',
    flexDirection: 'column',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 24px',
    height: 56,
    background: 'var(--bg-surface)',
    borderBottom: '1px solid var(--border)',
    position: 'sticky',
    top: 0,
    zIndex: 100,
  },
  headerLeft: { display: 'flex', alignItems: 'center', gap: 16 },
  logo:       { display: 'flex', alignItems: 'center', gap: 8 },
  logoIcon:   { fontSize: 18, color: 'var(--teal)' },
  logoText: {
    fontFamily: 'var(--mono)',
    fontWeight: 600,
    fontSize: 14,
    color: 'var(--text-primary)',
    letterSpacing: '0.02em',
  },
  badge: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '3px 10px',
    background: 'var(--green-dim)',
    border: '1px solid var(--green)',
    borderRadius: 20,
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--green)',
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    display: 'inline-block',
  },
  headerRight: { display: 'flex', alignItems: 'center', gap: 12 },
  updated: {
    fontFamily: 'var(--mono)',
    fontSize: 11,
    color: 'var(--text-tertiary)',
  },
  pill: {
    padding: '4px 12px',
    background: 'var(--teal-dim)',
    border: '1px solid var(--teal)',
    borderRadius: 20,
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--teal)',
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
  },
  errorBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 24px',
    background: 'var(--red-dim)',
    borderBottom: '1px solid var(--red)',
    fontSize: 12,
    color: 'var(--red)',
    fontFamily: 'var(--mono)',
  },
  errorIcon:  { fontSize: 14 },
  errorHint:  { marginLeft: 'auto', color: 'var(--text-secondary)', fontSize: 11 },
  main: {
    flex: 1,
    padding: '20px 24px',
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
}