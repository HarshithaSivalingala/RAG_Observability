function Skeleton({ w = '60%', h = 28 }) {
  return (
    <div
      className="skeleton"
      style={{ width: w, height: h }}
      aria-hidden="true"
    />
  )
}

function fmt(val, decimals = 0) {
  if (val == null) return '—'
  return Number(val).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

function Card({ label, value, unit = '', accent, sub, loading }) {
  return (
    <div
      style={{ ...s.card, borderTopColor: accent }}
      role="region"
      aria-label={label}
    >
      <div style={s.topRow}>
        <span style={s.label}>{label}</span>
        <div style={{ ...s.accentDot, background: accent }} />
      </div>

      {loading ? (
        <>
          <Skeleton w="55%" h={28} />
          <Skeleton w="40%" h={10} />
        </>
      ) : (
        <>
          <div style={s.valueRow}>
            <span style={{ ...s.value, color: accent }}>{value}</span>
            {unit && <span style={s.unit}>{unit}</span>}
          </div>
          {sub && <div style={s.sub}>{sub}</div>}
        </>
      )}
    </div>
  )
}

export default function MetricCards({ metrics, loading }) {
  const m = metrics || {}

  const errorAccent =
    (m.error_rate ?? 0) > 5  ? 'var(--red)' :
    (m.error_rate ?? 0) > 2  ? 'var(--yellow)' :
    'var(--green)'

  const cacheAccent =
    (m.cache_hit_rate ?? 0) > 50 ? 'var(--green)' : 'var(--teal)'

  return (
    <div className="metric-grid">
      <Card
        label="Total Queries"
        value={fmt(m.total_queries)}
        accent="var(--teal)"
        sub={`${fmt(m.slow_query_count)} slow`}
        loading={loading}
      />
      <Card
        label="p50 Latency"
        value={fmt(m.p50_latency_ms, 1)}
        unit="ms"
        accent="var(--blue)"
        sub="median response"
        loading={loading}
      />
      <Card
        label="p95 Latency"
        value={fmt(m.p95_latency_ms, 1)}
        unit="ms"
        accent="var(--blue)"
        sub="95th percentile"
        loading={loading}
      />
      <Card
        label="Error Rate"
        value={fmt(m.error_rate, 1)}
        unit="%"
        accent={errorAccent}
        sub={`${fmt(m.empty_response_count)} empty responses`}
        loading={loading}
      />
      <Card
        label="Cache Hit Rate"
        value={fmt(m.cache_hit_rate, 1)}
        unit="%"
        accent={cacheAccent}
        sub="served from cache"
        loading={loading}
      />
    </div>
  )
}

const s = {
  card: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderTop: '2px solid transparent',
    borderRadius: 'var(--radius-lg)',
    padding: '16px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  topRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  label: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  accentDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    opacity: 0.8,
  },
  valueRow: {
    display: 'flex',
    alignItems: 'baseline',
    gap: 4,
  },
  value: {
    fontFamily: 'var(--mono)',
    fontSize: 28,
    fontWeight: 600,
    lineHeight: 1,
    letterSpacing: '-0.02em',
  },
  unit: {
    fontFamily: 'var(--mono)',
    fontSize: 12,
    color: 'var(--text-secondary)',
  },
  sub: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    color: 'var(--text-tertiary)',
  },
}