import { useState, useEffect, useCallback } from 'react'
import BrevoStatsPanel from './BrevoStatsPanel'

function Badge({ label, color }) {
  const colors = {
    live: 'bg-green-accent/15 text-green-accent border-green-accent/30',
    dry: 'bg-amber-accent/15 text-amber-accent border-amber-accent/30',
    auto: 'bg-purple-primary/15 text-purple-light border-purple-primary/30',
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

function RunCard({ run }) {
  const [expanded, setExpanded] = useState(false)

  const ts = run.timestamp
    ? new Date(run.timestamp).toLocaleString('en-IN', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit', hour12: true,
      })
    : 'Unknown'

  const runDate = run.date || (run.timestamp ? run.timestamp.split('T')[0] : null)

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
          </div>
          <p className="text-xs text-text-muted mt-0.5">{run.duration_min ? `${run.duration_min} min` : ''}</p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0 flex-wrap justify-end">
          <StatPill label="Scraped" value={run.scraped ?? 0} color="text-text-primary" />
          <StatPill label="Real" value={run.real ?? 0} color="text-purple-light" />
          <StatPill label="Enriched" value={run.enriched ?? 0} color="text-blue-400" />
          <StatPill label="Sent" value={run.sent ?? 0} color="text-green-accent" />
          <StatPill label="Failed" value={run.failed ?? 0} color={run.failed > 0 ? 'text-red-accent' : 'text-text-muted'} />
        </div>

        <div className="flex-shrink-0 text-text-muted text-sm ml-2 transition-transform" style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
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
            All previous runs — click any row to see Brevo delivery stats
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
