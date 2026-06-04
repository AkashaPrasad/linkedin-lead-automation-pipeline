import { useState, useEffect } from 'react'

function StatCard({ label, value, color = 'text-text-primary', sub }) {
  return (
    <div className="bg-bg-primary border border-border-color rounded-xl p-4 flex flex-col gap-1">
      <div className={`text-2xl font-bold ${color}`}>{value ?? '—'}</div>
      <div className="text-xs text-text-muted">{label}</div>
      {sub != null && <div className="text-xs text-text-secondary">{sub}</div>}
    </div>
  )
}

function pct(part, total) {
  if (!total || total === 0) return null
  return `${Math.round((part / total) * 100)}%`
}

export default function BrevoStatsPanel({ date }) {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    const url = date ? `/api/brevo/stats?date=${date}` : '/api/brevo/stats'
    fetch(url)
      .then(r => r.json())
      .then(data => {
        if (data.error) {
          setError(data.error)
        } else {
          setStats(data)
        }
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
  }, [date])

  const displayDate = date || new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })

  return (
    <div className="bg-bg-secondary border border-border-color rounded-xl h-full flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-color flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-base">📬</span>
          <span className="text-sm font-semibold text-text-primary">Brevo Email Stats</span>
          <span className="text-xs text-text-muted">— {displayDate}</span>
        </div>
        <span className="text-xs text-text-muted italic">All emails sent today</span>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {loading && (
          <div className="h-full flex items-center justify-center">
            <div className="w-5 h-5 border-2 border-purple-primary border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {error && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center text-text-muted">
              <div className="text-2xl mb-2">⚠</div>
              <p className="text-xs">Could not load Brevo stats</p>
              <p className="text-xs text-text-muted mt-1 max-w-[200px] text-center">{error}</p>
            </div>
          </div>
        )}

        {!loading && !error && stats && (
          <div className="space-y-4">
            {/* Primary stats */}
            <div className="grid grid-cols-3 gap-3">
              <StatCard
                label="Sent"
                value={stats.requests ?? 0}
                color="text-purple-light"
              />
              <StatCard
                label="Delivered"
                value={stats.delivered ?? 0}
                color="text-green-accent"
                sub={pct(stats.delivered, stats.requests) ? `${pct(stats.delivered, stats.requests)} delivery rate` : null}
              />
              <StatCard
                label="Bounced"
                value={(stats.hardBounces ?? 0) + (stats.softBounces ?? 0)}
                color={(stats.hardBounces ?? 0) + (stats.softBounces ?? 0) > 0 ? 'text-red-accent' : 'text-text-secondary'}
                sub={stats.hardBounces != null ? `${stats.hardBounces} hard · ${stats.softBounces} soft` : null}
              />
            </div>

            {/* Engagement stats */}
            <div className="grid grid-cols-3 gap-3">
              <StatCard
                label="Unique Opens"
                value={stats.uniqueOpens ?? 0}
                color="text-blue-400"
                sub={pct(stats.uniqueOpens, stats.delivered) ? `${pct(stats.uniqueOpens, stats.delivered)} open rate` : null}
              />
              <StatCard
                label="Unique Clicks"
                value={stats.uniqueClicks ?? 0}
                color="text-blue-400"
                sub={pct(stats.uniqueClicks, stats.delivered) ? `${pct(stats.uniqueClicks, stats.delivered)} click rate` : null}
              />
              <StatCard
                label="Unsubscribed"
                value={stats.unsubscribed ?? 0}
                color={stats.unsubscribed > 0 ? 'text-amber-accent' : 'text-text-secondary'}
              />
            </div>

            {/* Secondary stats */}
            <div className="grid grid-cols-3 gap-3">
              <StatCard
                label="Spam Reports"
                value={stats.spamReports ?? 0}
                color={stats.spamReports > 0 ? 'text-red-accent' : 'text-text-secondary'}
              />
              <StatCard
                label="Blocked"
                value={stats.blocked ?? 0}
                color={stats.blocked > 0 ? 'text-amber-accent' : 'text-text-secondary'}
              />
              <StatCard
                label="Invalid"
                value={stats.invalid ?? 0}
                color={stats.invalid > 0 ? 'text-amber-accent' : 'text-text-secondary'}
              />
            </div>
          </div>
        )}

        {!loading && !error && !stats && (
          <div className="h-full flex items-center justify-center text-text-muted text-xs">
            No data available
          </div>
        )}
      </div>
    </div>
  )
}
