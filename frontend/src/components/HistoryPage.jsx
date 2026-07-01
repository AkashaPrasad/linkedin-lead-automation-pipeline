import { useState, useEffect, useCallback } from 'react'
import BrevoStatsPanel from './BrevoStatsPanel'

function Badge({ label, color }) {
  const colors = {
    live: 'bg-green-accent/15 text-green-accent border-green-accent/30',
    dry: 'bg-amber-accent/15 text-amber-accent border-amber-accent/30',
    auto: 'bg-purple-primary/15 text-purple-light border-purple-primary/30',
    failed: 'bg-red-accent/15 text-red-accent border-red-accent/30',
    stopped: 'bg-amber-accent/15 text-amber-accent border-amber-accent/30',
    unknown: 'bg-text-muted/15 text-text-muted border-text-muted/30',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${colors[color] || colors.live}`}>
      {label}
    </span>
  )
}

function StatPill({ label, value, color = 'text-text-primary' }) {
  return (
    <div className="flex flex-col items-center bg-bg-primary border border-border-color rounded-lg px-4 py-2.5 min-w-[80px]">
      <span className={`text-lg font-bold ${color}`}>{value}</span>
      <span className="text-xs text-text-muted mt-0.5 text-center">{label}</span>
    </div>
  )
}

// ── Converts a raw SSE event (as stored in a run's log) into a readable line,
// mirroring the same formatting App.jsx uses for the live LogConsole. ─────────
function eventToLine(event, i) {
  const ev = event.event
  switch (ev) {
    case 'stage_start':
      return { id: i, level: 'INFO', message: `Stage ${event.stage}: ${event.name} — ${event.message || ''}` }
    case 'stage_complete':
      return { id: i, level: 'INFO', message: `✅ Stage ${event.stage} complete — ${event.metric || ''}` }
    case 'progress':
      return { id: i, level: 'INFO', message: event.message || '' }
    case 'log':
      return { id: i, level: event.level || 'INFO', message: event.message || '' }
    case 'lead':
      return { id: i, level: 'INFO', message: `📧 ${event.name || ''} — ${event.category || ''} — ${event.status || ''} (${event.email || ''})` }
    case 'complete':
      return { id: i, level: 'INFO', message: `🎯 Pipeline complete — ${event.sent ?? 0} sent, ${event.failed ?? 0} failed, ${event.no_email ?? 0} no email` }
    case 'error':
      return { id: i, level: 'ERROR', message: `❌ Pipeline error: ${event.message || ''}` }
    case 'stopped':
      return { id: i, level: 'WARN', message: `🛑 ${event.message || 'Pipeline stopped'}` }
    case 'heartbeat':
    case 'stats':
      return null
    default:
      return { id: i, level: 'INFO', message: JSON.stringify(event) }
  }
}

const LEVEL_COLORS = {
  INFO: 'text-text-secondary',
  WARN: 'text-amber-accent',
  WARNING: 'text-amber-accent',
  ERROR: 'text-red-accent',
  DEBUG: 'text-text-muted',
}

function RunLogsModal({ runId, onClose }) {
  const [lines, setLines] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`/api/history/${runId}/logs`)
      .then(r => {
        if (!r.ok) throw new Error(r.status === 404 ? 'No logs found for this run' : `Server error ${r.status}`)
        return r.json()
      })
      .then(data => {
        const formatted = (data.events || [])
          .map((e, i) => eventToLine(e, i))
          .filter(Boolean)
        setLines(formatted)
      })
      .catch(e => setError(e.message))
  }, [runId])

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-bg-secondary border border-border-color rounded-2xl w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-color flex-shrink-0">
          <div>
            <h3 className="text-base font-bold text-text-primary">Run Logs</h3>
            <p className="text-xs text-text-muted mt-0.5 font-mono">#{runId}</p>
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary transition-colors">
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed bg-[#0D0D14]">
          {error && <p className="text-red-accent">{error}</p>}
          {!error && lines === null && <p className="text-text-muted">Loading logs...</p>}
          {!error && lines !== null && lines.length === 0 && (
            <p className="text-text-muted">No log lines recorded for this run.</p>
          )}
          {!error && lines !== null && lines.map(l => (
            <div key={l.id} className="flex gap-3">
              <span className={`flex-shrink-0 ${LEVEL_COLORS[l.level] || 'text-text-muted'} opacity-60`}>
                {(l.level || 'LOG').padEnd(5, ' ')}
              </span>
              <span className={LEVEL_COLORS[l.level] || 'text-text-secondary'}>{l.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function RunCard({ run }) {
  const [expanded, setExpanded] = useState(false)
  const [showLogs, setShowLogs] = useState(false)

  const ts = run.timestamp
    ? new Date(run.timestamp).toLocaleString('en-IN', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit', hour12: true,
      })
    : 'Unknown'

  const runDate = run.date || (run.timestamp ? run.timestamp.split('T')[0] : null)
  const status = run.status || 'completed'
  const statusLabel = { completed: null, failed: 'Failed', stopped: 'Stopped', unknown: 'Unknown' }[status]

  return (
    <div className="bg-bg-secondary border border-border-color rounded-xl overflow-hidden transition-all">
      {/* Header row */}
      <div
        className="flex items-center gap-4 px-5 py-4 cursor-pointer hover:bg-bg-tertiary/50 transition-colors select-none"
        onClick={() => setExpanded(p => !p)}
      >
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-purple-primary/10 border border-purple-primary/20 flex items-center justify-center">
          <span className="text-xs font-bold text-purple-light font-mono">#{run.id?.slice(0, 4) || '??'}</span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-text-primary">{ts}</span>
            {run.dry_run
              ? <Badge label="Dry Run" color="dry" />
              : <Badge label="Live" color="live" />
            }
            {statusLabel && <Badge label={statusLabel} color={status} />}
          </div>
          <p className="text-xs text-text-muted mt-0.5">
            {run.duration_min ? `${run.duration_min} min` : ''}
            {run.error_message && <span className="text-red-accent"> — {run.error_message.slice(0, 100)}</span>}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0 flex-wrap justify-end">
          <StatPill label="Scraped" value={run.scraped ?? 0} color="text-text-primary" />
          <StatPill label="Real" value={run.real ?? 0} color="text-purple-light" />
          <StatPill label="Enriched" value={run.enriched ?? 0} color="text-blue-400" />
          <StatPill label="Sent" value={run.sent ?? 0} color="text-green-accent" />
          <StatPill label="Failed" value={run.failed ?? 0} color={run.failed > 0 ? 'text-red-accent' : 'text-text-muted'} />
        </div>

        <button
          onClick={e => { e.stopPropagation(); setShowLogs(true) }}
          className="flex-shrink-0 px-3 py-1.5 rounded-lg bg-bg-tertiary border border-border-color text-text-secondary text-xs font-medium hover:text-text-primary hover:border-purple-primary/40 transition-colors"
        >
          View Logs
        </button>

        <div className="flex-shrink-0 text-text-muted text-sm ml-1 transition-transform" style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
          ▾
        </div>
      </div>

      {/* Expanded Brevo stats */}
      {expanded && (
        <div className="border-t border-border-color px-5 pb-5 pt-4">
          <p className="text-xs text-text-muted mb-3 font-medium uppercase tracking-wider">Brevo Delivery Stats — {runDate || 'today'}</p>
          <div className="h-64">
            <BrevoStatsPanel date={runDate} />
          </div>
        </div>
      )}

      {showLogs && <RunLogsModal runId={run.id} onClose={() => setShowLogs(false)} />}
    </div>
  )
}

export default function HistoryPage() {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchHistory = useCallback(() => {
    setLoading(true)
    fetch('/api/history')
      .then(r => r.json())
      .then(data => {
        setRuns(Array.isArray(data) ? data : [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  return (
    <div className="h-full flex flex-col overflow-hidden p-6 gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-lg font-bold text-text-primary">Pipeline History</h2>
          <p className="text-xs text-text-muted mt-0.5">
            All previous runs (dry or real) — click "View Logs" for the full run transcript, or a row for Brevo delivery stats
          </p>
        </div>
        <button
          onClick={fetchHistory}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-bg-tertiary border border-border-color text-text-secondary text-sm hover:text-text-primary hover:border-purple-primary/40 transition-colors disabled:opacity-50"
        >
          {loading ? (
            <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
          ) : (
            <span className="text-xs">↻</span>
          )}
          Refresh
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {loading && (
          <div className="flex items-center justify-center h-40">
            <div className="w-6 h-6 border-2 border-purple-primary border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {!loading && runs.length === 0 && (
          <div className="flex flex-col items-center justify-center h-40 text-text-muted">
            <div className="text-4xl mb-3">📭</div>
            <p className="text-sm">No pipeline runs yet</p>
            <p className="text-xs mt-1">Run the pipeline from the Dashboard to see history here</p>
          </div>
        )}

        {!loading && runs.map(run => (
          <RunCard key={run.id} run={run} />
        ))}
      </div>
    </div>
  )
}
