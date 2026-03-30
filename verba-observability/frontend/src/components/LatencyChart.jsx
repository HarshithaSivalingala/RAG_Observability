import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceDot
} from 'recharts'

// Use CSS variable values for chart colors so they stay in sync with the theme.
// Recharts cannot read CSS variables directly, so we pull them at render time.
function cssVar(name) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name).trim()
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  return (
    <div style={s.tooltip}>
      <div style={s.tooltipLabel}>Query #{d.index}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={s.tooltipRow}>
          <span style={{ color: p.color }}>{p.name}</span>
          <span style={s.tooltipVal}>{p.value.toFixed(1)}ms</span>
        </div>
      ))}
      {d.slow && (
        <div style={s.tooltipSlow}>🐢 Slow query (&gt;10s)</div>
      )}
    </div>
  )
}

export default function LatencyChart({ data, loading }) {
  // Keep full float precision — rounding before charting flattens real differences
  const points = (data || []).map((d, i) => ({
    index: i + 1,
    total: d.total_latency_ms,         // keep as float
    retrieval: d.retrieval_latency_ms || 0,
    llm: d.llm_latency_ms || 0,
    slow: d.is_slow_query === 1,
  }))

  const slowPoints = points.filter(p => p.slow)

  const avgTotal = points.length
    ? points.reduce((s, p) => s + p.total, 0) / points.length
    : 0

  const teal = '#00c4b4'   // matches --teal
  const blue = '#4d9cff'   // matches --blue
  const red  = '#f85149'   // matches --red

  const Panel = ({ children }) => (
    <div style={s.panel}>
      <div style={s.panelHeader}>
        <span style={s.panelTitle}>Latency Over Time</span>
        <div style={s.headerRight}>
          {slowPoints.length > 0 && (
            <span style={s.slowBadge} aria-label={`${slowPoints.length} slow queries`}>
              🐢 {slowPoints.length} slow
            </span>
          )}
          <span style={s.avgBadge}>
            avg {avgTotal.toFixed(0)}ms
          </span>
        </div>
      </div>
      {children}
    </div>
  )

  if (loading) {
    return (
      <Panel>
        <div className="skeleton" style={{ height: 220, borderRadius: 6 }} />
      </Panel>
    )
  }

  if (points.length === 0) {
    return (
      <Panel>
        <div style={s.empty}>No query data yet — ask something in Verba!</div>
      </Panel>
    )
  }

  return (
    <Panel>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 16 }}>
          <defs>
            <linearGradient id="gradTotal" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={teal} stopOpacity={0.3} />
              <stop offset="95%" stopColor={teal} stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gradLLM" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={blue} stopOpacity={0.2} />
              <stop offset="95%" stopColor={blue} stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#1e2530" vertical={false} />

          <XAxis
            dataKey="index"
            tick={{ fill: '#484f58', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            axisLine={false}
            tickLine={false}
            label={{ value: 'Query #', position: 'insideBottom', offset: -8, fill: '#484f58', fontSize: 10 }}
          />
          <YAxis
            tick={{ fill: '#484f58', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={v => `${v.toFixed(0)}ms`}
            width={60}
          />

          <Tooltip content={<CustomTooltip />} />

          <Area
            type="monotone"
            dataKey="total"
            name="Total"
            stroke={teal}
            strokeWidth={2}
            fill="url(#gradTotal)"
            dot={false}
            activeDot={{ r: 4, fill: teal }}
          />
          <Area
            type="monotone"
            dataKey="llm"
            name="LLM"
            stroke={blue}
            strokeWidth={1.5}
            fill="url(#gradLLM)"
            dot={false}
            activeDot={{ r: 3, fill: blue }}
            strokeDasharray="4 2"
          />

          {/* Visually mark slow queries as red dots on the total line */}
          {slowPoints.map(p => (
            <ReferenceDot
              key={p.index}
              x={p.index}
              y={p.total}
              r={5}
              fill={red}
              stroke="#0d1117"
              strokeWidth={2}
              label={null}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </Panel>
  )
}

const s = {
  panel: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: '16px 18px',
  },
  panelHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  panelTitle: {
    fontFamily: 'var(--mono)',
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
  },
  headerRight: { display: 'flex', alignItems: 'center', gap: 8 },
  avgBadge: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    color: 'var(--teal)',
    background: 'var(--teal-dim)',
    padding: '2px 8px',
    borderRadius: 10,
    border: '1px solid rgba(0,196,180,0.3)',
  },
  slowBadge: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    color: 'var(--red)',
    background: 'var(--red-dim)',
    padding: '2px 8px',
    borderRadius: 10,
    border: '1px solid rgba(248,81,73,0.3)',
  },
  empty: {
    height: 220,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'var(--text-tertiary)',
    fontFamily: 'var(--mono)',
    fontSize: 12,
  },
  tooltip: {
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    borderRadius: 6,
    padding: '8px 12px',
    fontSize: 11,
    fontFamily: 'var(--mono)',
    minWidth: 140,
  },
  tooltipLabel: {
    color: 'var(--text-secondary)',
    marginBottom: 6,
    fontSize: 10,
  },
  tooltipRow: {
    display: 'flex',
    justifyContent: 'space-between',
    gap: 12,
    padding: '2px 0',
  },
  tooltipVal: {
    color: 'var(--text-primary)',
    fontWeight: 600,
  },
  tooltipSlow: {
    marginTop: 6,
    paddingTop: 6,
    borderTop: '1px solid var(--border-subtle)',
    color: 'var(--red)',
    fontSize: 10,
  },
}