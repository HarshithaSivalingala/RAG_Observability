import { useState, useCallback,Fragment } from 'react'

// ── Category badge ────────────────────────────────────────────────────────────
const CATEGORY_COLORS = {
  financial:  { bg: 'rgba(0,196,180,0.12)',  color: '#00c4b4' },
  compliance: { bg: 'rgba(77,156,255,0.12)', color: '#4d9cff' },
  analytical: { bg: 'rgba(210,153,34,0.12)', color: '#d29922' },
  factual:    { bg: 'rgba(63,185,80,0.12)',  color: '#3fb950' },
  general:    { bg: 'rgba(125,133,144,0.12)',color: '#7d8590' },
}

function CategoryBadge({ category }) {
  const c = CATEGORY_COLORS[category] || CATEGORY_COLORS.general
  return (
    <span
      style={{ ...s.badge, background: c.bg, color: c.color, border: `1px solid ${c.color}40` }}
      aria-label={`Category: ${category}`}
    >
      {category}
    </span>
  )
}

// ── Status cell ───────────────────────────────────────────────────────────────
function StatusCell({ row }) {
  if (row.error) {
    const label = row.error_type
      ? `${row.error_type}: ${row.error.slice(0, 40)}`
      : row.error.slice(0, 40)
    return (
      <div style={s.statusError} title={row.error} aria-label={`Error: ${row.error}`}>
        <span>✗</span>
        <span>{row.error_type || 'error'}</span>
      </div>
    )
  }
  if (row.is_empty_response) {
    return <div style={s.statusWarn} aria-label="Empty response">⊘ empty</div>
  }
  if (row.cache_hit) {
    return <div style={s.statusCache} aria-label="Served from cache">⚡ cached</div>
  }
  return <div style={s.statusOk} aria-label="Success">✓ ok</div>
}

// ── Latency cell ──────────────────────────────────────────────────────────────
function LatencyCell({ ms }) {
  const isSlow = ms > 10000
  const isMed  = ms > 5000
  const color  = isSlow ? 'var(--red)' : isMed ? 'var(--yellow)' : 'var(--text-secondary)'
  return (
    <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color }} aria-label={`${(ms/1000).toFixed(2)} seconds`}>
      {isSlow && '🐢 '}{(ms / 1000).toFixed(2)}s
    </span>
  )
}

// ── Expandable detail panel ───────────────────────────────────────────────────
function DetailPanel({ row }) {
  return (
    <tr>
      <td colSpan={7} style={s.detailCell}>
        <div style={s.detail}>
          <div style={s.detailSection}>
            <span style={s.detailLabel}>Full question</span>
            <p style={s.detailText}>{row.question}</p>
          </div>

          {row.response && (
            <div style={s.detailSection}>
              <span style={s.detailLabel}>Response preview</span>
              <p style={s.detailText}>{row.response.slice(0, 300)}{row.response.length > 300 ? '…' : ''}</p>
            </div>
          )}

          <div style={s.detailGrid}>
            <div style={s.detailItem}>
              <span style={s.detailLabel}>Request ID</span>
              <span style={s.detailMono}>{row.id}</span>
            </div>
            <div style={s.detailItem}>
              <span style={s.detailLabel}>Session</span>
              <span style={s.detailMono}>{row.session_id || '—'}</span>
            </div>
            <div style={s.detailItem}>
              <span style={s.detailLabel}>Retrieval</span>
              <span style={s.detailMono}>{row.retrieval_latency_ms?.toFixed(1) || '—'}ms</span>
            </div>
            <div style={s.detailItem}>
              <span style={s.detailLabel}>LLM</span>
              <span style={s.detailMono}>{row.llm_latency_ms?.toFixed(1) || '—'}ms</span>
            </div>
            <div style={s.detailItem}>
              <span style={s.detailLabel}>Response length</span>
              <span style={s.detailMono}>{row.response_length} chars</span>
            </div>
          </div>

          {row.chunk_titles?.length > 0 && (
            <div style={s.detailSection}>
              <span style={s.detailLabel}>Retrieved documents</span>
              <div style={s.chunkList}>
                {row.chunk_titles.map((title, i) => (
                  <div key={i} style={s.chunkItem}>
                    <span style={s.chunkTitle}>{title}</span>
                    {row.chunk_scores?.[i] != null && (
                      <span style={s.chunkScore}>
                        {(row.chunk_scores[i] * 100).toFixed(1)}%
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {row.error && (
            <div style={s.detailSection}>
              <span style={s.detailLabel}>Error</span>
              <p style={{ ...s.detailText, color: 'var(--red)', fontFamily: 'var(--mono)', fontSize: 11 }}>
                [{row.error_type || 'unknown'}] {row.error}
              </p>
            </div>
          )}
        </div>
      </td>
    </tr>
  )
}

// ── Feedback buttons ──────────────────────────────────────────────────────────
function FeedbackButtons({ rowId, initial, onFeedback }) {
  const [state, setState] = useState(initial || null)
  // 'idle' | 'loading' | 'done' | 'error'
  const [status, setStatus] = useState('idle')

  const handleClick = useCallback(async (type) => {
    if (status === 'loading' || state === type) return
    setStatus('loading')
    const result = await onFeedback(rowId, type)
    if (result.ok) {
      setState(type)
      setStatus('done')
    } else {
      setStatus('error')
      setTimeout(() => setStatus('idle'), 2000)
    }
  }, [rowId, state, status, onFeedback])

  return (
    <div style={s.fbRow} role="group" aria-label="Response feedback">
      {['thumbs_up', 'thumbs_down'].map(type => {
        const isActive  = state === type
        const isLoading = status === 'loading'
        const isError   = status === 'error'
        const emoji = type === 'thumbs_up' ? '👍' : '👎'
        const activeStyle = type === 'thumbs_up' ? s.fbActiveUp : s.fbActiveDown

        return (
          <button
            key={type}
            onClick={() => handleClick(type)}
            disabled={isLoading || state != null}
            style={{
              ...s.fbBtn,
              ...(isActive ? activeStyle : {}),
              ...(isError ? s.fbError : {}),
            }}
            aria-label={type === 'thumbs_up' ? 'Mark as good' : 'Mark as bad'}
            aria-pressed={isActive}
            title={
              state != null
                ? 'Feedback already submitted'
                : isLoading
                  ? 'Saving…'
                  : type === 'thumbs_up' ? 'Good response' : 'Bad response'
            }
          >
            {isLoading ? '…' : emoji}
          </button>
        )
      })}
    </div>
  )
}

// ── Main table ────────────────────────────────────────────────────────────────
const SORT_OPTIONS = [
  { value: 'newest',  label: 'Newest first' },
  { value: 'oldest',  label: 'Oldest first' },
  { value: 'slowest', label: 'Slowest first' },
  { value: 'fastest', label: 'Fastest first' },
]

export default function QueryTable({ queries, loading, onFeedback }) {
  const [sort, setSort] = useState('newest')
  const [expanded, setExpanded] = useState(null)

  const rows = [...(queries || [])].sort((a, b) => {
    if (sort === 'newest')  return new Date(b.timestamp) - new Date(a.timestamp)
    if (sort === 'oldest')  return new Date(a.timestamp) - new Date(b.timestamp)
    if (sort === 'slowest') return b.total_latency_ms - a.total_latency_ms
    if (sort === 'fastest') return a.total_latency_ms - b.total_latency_ms
    return 0
  })

  const toggleRow = (id) => setExpanded(e => e === id ? null : id)

  return (
    <div style={s.panel}>
      <div style={s.panelHeader}>
        <span style={s.panelTitle}>Query History</span>
        <div style={s.headerControls}>
          <span style={s.count}>{rows.length} queries</span>
          <select
            value={sort}
            onChange={e => setSort(e.target.value)}
            style={s.sortSelect}
            aria-label="Sort queries"
          >
            {SORT_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div style={s.tableWrapper} role="region" aria-label="Query history table">
        <table style={s.table} aria-label="Query history">
          <thead>
            <tr>
              {['Time', 'Question', 'Category', 'Latency', 'Chunks', 'Status', 'Feedback'].map(h => (
                <th key={h} style={s.th} scope="col">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>
                  {Array.from({ length: 7 }).map((_, j) => (
                    <td key={j} style={s.td}>
                      <div className="skeleton" style={{ height: 12, width: j === 1 ? '80%' : '60%' }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} style={s.empty}>
                  No queries yet — ask something in Verba at localhost:8001!
                </td>
              </tr>
            ) : (
              rows.map((q, i) => {
                const isExpanded = expanded === q.id
                const ts = new Date(q.timestamp)
                return (
                  <Fragment key={q.id}>
                    <tr
                      
                      style={{
                        ...s.tr,
                        background: i % 2 === 0 ? 'transparent' : 'var(--bg-elevated)',
                        borderLeft: q.is_slow_query ? '2px solid var(--red)' : '2px solid transparent',
                        cursor: 'pointer',
                      }}
                      onClick={() => toggleRow(q.id)}
                      aria-expanded={isExpanded}
                      title="Click to expand details"
                    >
                      <td style={s.td}>
                        <div style={s.timeCell}>
                          <span style={s.timeDate}>{ts.toLocaleDateString()}</span>
                          <span style={s.timeClock}>{ts.toLocaleTimeString()}</span>
                        </div>
                      </td>
                      <td style={s.tdQuestion}>
                        <span style={s.question} title={q.question}>
                          {q.question?.length > 48
                            ? q.question.slice(0, 48) + '…'
                            : q.question}
                        </span>
                      </td>
                      <td style={s.td}>
                        <CategoryBadge category={q.query_category} />
                      </td>
                      <td style={s.td}>
                        <LatencyCell ms={q.total_latency_ms} />
                      </td>
                      <td style={s.td}>
                        <span style={s.mono}>{q.chunks_retrieved}</span>
                      </td>
                      <td style={s.td}>
                        <StatusCell row={q} />
                      </td>
                      <td style={s.td} onClick={e => e.stopPropagation()}>
                        <FeedbackButtons
                          rowId={q.id}
                          initial={q.feedback}
                          onFeedback={onFeedback}
                        />
                      </td>
                    </tr>
                    {isExpanded && <DetailPanel key={`${q.id}-detail`} row={q} />}
                  </Fragment>
                )
              })
            )}
          </tbody>
        </table>
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
  headerControls: { display: 'flex', alignItems: 'center', gap: 10 },
  count: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    color: 'var(--text-tertiary)',
    background: 'var(--bg-elevated)',
    padding: '2px 8px',
    borderRadius: 10,
  },
  sortSelect: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    color: 'var(--text-secondary)',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    borderRadius: 6,
    padding: '3px 8px',
    outline: 'none',
    cursor: 'pointer',
  },
  tableWrapper: {
    overflowX: 'auto',
    maxHeight: 380,
    overflowY: 'auto',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
  },
  th: {
    fontFamily: 'var(--mono)',
    fontSize: 9,
    fontWeight: 600,
    color: 'var(--text-tertiary)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    padding: '8px 14px',
    textAlign: 'left',
    background: 'var(--bg-elevated)',
    borderBottom: '1px solid var(--border)',
    position: 'sticky',
    top: 0,
    zIndex: 1,
    whiteSpace: 'nowrap',
  },
  tr: { transition: 'background 0.1s' },
  td: {
    padding: '8px 14px',
    borderBottom: '1px solid var(--border-subtle)',
    verticalAlign: 'middle',
  },
  tdQuestion: {
    padding: '8px 14px',
    borderBottom: '1px solid var(--border-subtle)',
    verticalAlign: 'middle',
    maxWidth: 260,
  },
  timeCell: { display: 'flex', flexDirection: 'column', gap: 1 },
  timeDate: { fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-tertiary)' },
  timeClock: { fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-secondary)' },
  question: { fontSize: 12, color: 'var(--text-primary)' },
  badge: {
    fontFamily: 'var(--mono)',
    fontSize: 9,
    fontWeight: 600,
    padding: '2px 7px',
    borderRadius: 10,
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
  },
  mono: { fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-secondary)' },
  statusOk:    { fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--green)' },
  statusError: {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    color: 'var(--red)',
    display: 'flex',
    flexDirection: 'column',
    gap: 1,
  },
  statusWarn:  { fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--yellow)' },
  statusCache: { fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--teal)' },
  fbRow: { display: 'flex', gap: 4 },
  fbBtn: {
    background: 'none',
    border: '1px solid var(--border)',
    borderRadius: 6,
    padding: '2px 7px',
    fontSize: 11,
    opacity: 0.5,
    transition: 'all 0.15s',
    minWidth: 30,
  },
  fbActiveUp:   { opacity: 1, background: 'var(--green-dim)', borderColor: 'var(--green)' },
  fbActiveDown: { opacity: 1, background: 'var(--red-dim)',   borderColor: 'var(--red)' },
  fbError:      { opacity: 1, background: 'var(--yellow-dim)', borderColor: 'var(--yellow)' },
  empty: {
    padding: '32px',
    textAlign: 'center',
    color: 'var(--text-tertiary)',
    fontFamily: 'var(--mono)',
    fontSize: 12,
  },
  detailCell: {
    background: 'var(--bg-elevated)',
    borderBottom: '1px solid var(--border)',
    padding: 0,
  },
  detail: {
    padding: '16px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    borderLeft: '2px solid var(--teal)',
  },
  detailSection: { display: 'flex', flexDirection: 'column', gap: 4 },
  detailLabel: {
    fontFamily: 'var(--mono)',
    fontSize: 9,
    fontWeight: 600,
    color: 'var(--text-tertiary)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  detailText: { fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.5 },
  detailMono: { fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-secondary)' },
  detailGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
    gap: 8,
  },
  detailItem: { display: 'flex', flexDirection: 'column', gap: 2 },
  chunkList: { display: 'flex', flexDirection: 'column', gap: 4 },
  chunkItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    background: 'var(--bg-surface)',
    borderRadius: 4,
    padding: '4px 8px',
  },
  chunkTitle: { fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-primary)' },
  chunkScore: { fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--teal)' },
}