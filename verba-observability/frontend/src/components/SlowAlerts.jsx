export default function SlowAlerts({ queries, loading }) {
  const rows = queries || []

  return (
    <div style={s.panel} role="region" aria-label="Slow query alerts">
      <div style={s.panelHeader}>
        <div style={s.titleRow}>
          <span style={s.alertIcon} aria-hidden="true">⚠</span>
          <span style={s.panelTitle}>Slow Query Alerts</span>
        </div>
        <span style={{
          ...s.countBadge,
          background: rows.length > 0 ? 'var(--red-dim)'    : 'var(--bg-elevated)',
          color:      rows.length > 0 ? 'var(--red)'         : 'var(--text-tertiary)',
          border:     rows.length > 0 ? '1px solid var(--red)' : '1px solid var(--border)',
        }}
          aria-label={`${rows.length} slow queries`}
        >
          {rows.length}
        </span>
      </div>

      <div style={s.body}>
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} style={{ ...s.alertRow, background: 'var(--bg-elevated)', borderLeft: '2px solid var(--border)' }}>
              <div className="skeleton" style={{ height: 14, width: '40%' }} />
              <div className="skeleton" style={{ height: 10, width: '80%' }} />
            </div>
          ))
        ) : rows.length === 0 ? (
          <div style={s.allGood}>
            <span style={s.allGoodIcon} aria-hidden="true">✓</span>
            <span style={s.allGoodText}>All queries within threshold</span>
            <span style={s.threshold}>threshold: 10s</span>
          </div>
        ) : (
          rows.map((q, i) => (
            <div key={q.id} style={s.alertRow} role="alert">
              <div style={s.alertTop}>
                <span style={s.alertLatency}>{(q.total_latency_ms / 1000).toFixed(1)}s</span>
                <span style={s.alertTime}>{new Date(q.timestamp).toLocaleTimeString()}</span>
              </div>
              <div style={s.alertQuestion} title={q.question}>
                {q.question?.length > 55 ? q.question.slice(0, 55) + '…' : q.question}
              </div>
              {q.error && (
                <div style={s.alertError} role="note">✗ {q.error.slice(0, 60)}</div>
              )}
            </div>
          ))
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
  titleRow: { display: 'flex', alignItems: 'center', gap: 6 },
  alertIcon: { fontSize: 12, color: 'var(--yellow)' },
  panelTitle: {
    fontFamily: 'var(--mono)',
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
  },
  countBadge: {
    fontFamily: 'var(--mono)',
    fontSize: 11,
    fontWeight: 700,
    padding: '2px 8px',
    borderRadius: 10,
    minWidth: 24,
    textAlign: 'center',
  },
  body: {
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    maxHeight: 300,
    overflowY: 'auto',
  },
  allGood: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '24px 0',
    gap: 4,
  },
  allGoodIcon: { fontSize: 20, color: 'var(--green)' },
  allGoodText: { fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-secondary)' },
  threshold: { fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-tertiary)', marginTop: 2 },
  alertRow: {
    background: 'var(--red-dim)',
    borderLeft: '2px solid var(--red)',
    borderRadius: 6,
    padding: '10px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  alertTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  alertLatency: { fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 700, color: 'var(--red)' },
  alertTime: { fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-tertiary)' },
  alertQuestion: { fontSize: 11, color: 'var(--text-primary)', lineHeight: 1.4 },
  alertError: { fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--red)', opacity: 0.8 },
}