export default function DocumentUsage({ chunks, loading }) {
  const rows = chunks || []
  const max  = rows.length > 0 ? rows[0].retrieval_count : 1

  return (
    <div style={s.panel}>
      <div style={s.panelHeader}>
        <span style={s.panelTitle}>Document Usage</span>
        <span style={s.sub}>{rows.length} docs</span>
      </div>

      <div style={s.body}>
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div className="skeleton" style={{ height: 12, width: '70%' }} />
              <div className="skeleton" style={{ height: 4 }} />
            </div>
          ))
        ) : rows.length === 0 ? (
          <div style={s.empty}>No retrieval data yet</div>
        ) : (
          rows.slice(0, 10).map((row, i) => {
            const pct  = (row.retrieval_count / max) * 100
            const name = row.document.length > 28
              ? row.document.slice(0, 28) + '…'
              : row.document
            const barColor =
              i === 0 ? 'var(--teal)' :
              i === 1 ? 'var(--blue)' :
              'var(--text-tertiary)'
            return (
              <div key={i} style={s.row} role="listitem">
                <div style={s.meta}>
                  <span style={s.docName} title={row.document}>{name}</span>
                  <span style={s.count} aria-label={`${row.retrieval_count} retrievals`}>
                    {row.retrieval_count}
                  </span>
                </div>
                <div style={s.barTrack} role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                  <div style={{ ...s.barFill, width: `${pct}%`, background: barColor }} />
                </div>
                <div style={s.scoreRow}>
                  <span style={s.scoreLabel}>avg score</span>
                  <span style={s.scoreVal}>{(row.avg_score * 100).toFixed(1)}%</span>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

const s = {
  panel: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    overflow: 'hidden',
  },
  panelHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '14px 18px',
    borderBottom: '1px solid var(--border)',
  },
  panelTitle: {
    fontFamily: 'var(--mono)',
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
  },
  sub: { fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-tertiary)' },
  body: { padding: '12px 18px', display: 'flex', flexDirection: 'column', gap: 12 },
  row:  { display: 'flex', flexDirection: 'column', gap: 4 },
  meta: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  docName: { fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-primary)' },
  count: { fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 600, color: 'var(--teal)' },
  barTrack: { height: 4, background: 'var(--bg-elevated)', borderRadius: 2, overflow: 'hidden' },
  barFill:  { height: '100%', borderRadius: 2, transition: 'width 0.4s ease' },
  scoreRow: { display: 'flex', justifyContent: 'space-between' },
  scoreLabel: { fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-tertiary)' },
  scoreVal:   { fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-secondary)' },
  empty: {
    padding: '24px',
    textAlign: 'center',
    color: 'var(--text-tertiary)',
    fontFamily: 'var(--mono)',
    fontSize: 12,
  },
}