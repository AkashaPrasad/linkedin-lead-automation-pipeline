import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  RefreshCw, Loader2, Inbox, ChevronDown, X, CalendarDays,
} from 'lucide-react'
import BrevoStatsPanel from './BrevoStatsPanel'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent } from '@/components/ui/collapsible'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

const BADGE_STYLES = {
  live: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  dry: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  auto: 'bg-primary/15 text-primary border-primary/30',
  failed: 'bg-destructive/15 text-destructive border-destructive/30',
  stopped: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  unknown: 'bg-muted-foreground/15 text-muted-foreground border-muted-foreground/30',
}

function Badge2({ label, color }) {
  return <Badge variant="outline" className={cn('font-medium', BADGE_STYLES[color] || BADGE_STYLES.live)}>{label}</Badge>
}

function StatPill({ label, value, color = 'text-foreground' }) {
  return (
    <div className="flex flex-col items-center bg-background border border-border rounded-lg px-4 py-2.5 min-w-[80px]">
      <span className={cn('text-lg font-bold tabular-nums', color)}>{value}</span>
      <span className="text-xs text-muted-foreground mt-0.5 text-center">{label}</span>
    </div>
  )
}

// ── Converts a raw SSE event (as stored in a run's log) into a readable line,
// mirroring the same formatting App.jsx uses for the live LogConsole. ───────
function eventToLine(event, i) {
  const ev = event.event
  switch (ev) {
    case 'stage_start':
      return { id: i, level: 'INFO', message: `Stage ${event.stage}: ${event.name} — ${event.message || ''}` }
    case 'stage_complete':
      return { id: i, level: 'INFO', message: `Stage ${event.stage} complete — ${event.metric || ''}` }
    case 'progress':
      return { id: i, level: 'INFO', message: event.message || '' }
    case 'log':
      return { id: i, level: event.level || 'INFO', message: event.message || '' }
    case 'lead':
      return { id: i, level: 'INFO', message: `${event.name || ''} — ${event.category || ''} — ${event.status || ''} (${event.email || ''})` }
    case 'complete':
      return { id: i, level: 'INFO', message: `Pipeline complete — ${event.sent ?? 0} sent, ${event.failed ?? 0} failed, ${event.no_email ?? 0} no email` }
    case 'error':
      return { id: i, level: 'ERROR', message: `Pipeline error: ${event.message || ''}` }
    case 'stopped':
      return { id: i, level: 'WARN', message: event.message || 'Pipeline stopped' }
    case 'heartbeat':
    case 'stats':
      return null
    default:
      return { id: i, level: 'INFO', message: JSON.stringify(event) }
  }
}

const LEVEL_COLORS = {
  INFO: 'text-muted-foreground',
  WARN: 'text-amber-400',
  WARNING: 'text-amber-400',
  ERROR: 'text-destructive',
  DEBUG: 'text-muted-foreground/60',
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
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl h-[85vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 py-4 border-b border-border flex-shrink-0">
          <DialogTitle className="font-mono text-sm">Run Logs — #{runId}</DialogTitle>
        </DialogHeader>

        <ScrollArea className="flex-1 bg-[#0a0a0f]">
          <div className="p-5 font-mono text-sm leading-relaxed">
            {error && <p className="text-destructive">{error}</p>}
            {!error && lines === null && <p className="text-muted-foreground">Loading logs...</p>}
            {!error && lines !== null && lines.length === 0 && (
              <p className="text-muted-foreground">No log lines recorded for this run.</p>
            )}
            {!error && lines !== null && lines.map(l => (
              <div key={l.id} className="flex gap-3">
                <span className={cn('flex-shrink-0 opacity-60', LEVEL_COLORS[l.level] || 'text-muted-foreground')}>
                  {(l.level || 'LOG').padEnd(5, ' ')}
                </span>
                <span className={LEVEL_COLORS[l.level] || 'text-muted-foreground'}>{l.message}</span>
              </div>
            ))}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
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
    <Card className="border-border/80 bg-card overflow-hidden">
      <div
        className="flex items-center gap-4 px-5 py-4 cursor-pointer hover:bg-secondary/40 transition-colors select-none"
        onClick={() => setExpanded(p => !p)}
      >
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
          <span className="text-xs font-bold text-primary font-mono">#{run.id?.slice(0, 4) || '??'}</span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-foreground">{ts}</span>
            {run.dry_run ? <Badge2 label="Dry Run" color="dry" /> : <Badge2 label="Live" color="live" />}
            {statusLabel && <Badge2 label={statusLabel} color={status} />}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {run.duration_min ? `${run.duration_min} min` : ''}
            {run.error_message && <span className="text-destructive"> — {run.error_message.slice(0, 100)}</span>}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0 flex-wrap justify-end">
          <StatPill label="Scraped" value={run.scraped ?? 0} />
          <StatPill label="Real" value={run.real ?? 0} color="text-primary" />
          <StatPill label="Enriched" value={run.enriched ?? 0} color="text-sky-400" />
          <StatPill label="Sent" value={run.sent ?? 0} color="text-emerald-400" />
          <StatPill label="Failed" value={run.failed ?? 0} color={run.failed > 0 ? 'text-destructive' : 'text-muted-foreground'} />
        </div>

        <Button
          variant="outline" size="sm"
          onClick={e => { e.stopPropagation(); setShowLogs(true) }}
          className="flex-shrink-0"
        >
          View Logs
        </Button>

        <ChevronDown className={cn('flex-shrink-0 w-4 h-4 text-muted-foreground transition-transform', expanded && 'rotate-180')} />
      </div>

      <Collapsible open={expanded}>
        <CollapsibleContent>
          <div className="border-t border-border px-5 pb-5 pt-4">
            <p className="text-xs text-muted-foreground mb-3 font-medium uppercase tracking-wider">Brevo Delivery Stats — {runDate || 'today'}</p>
            <div className="h-64">
              <BrevoStatsPanel date={runDate} />
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>

      {showLogs && <RunLogsModal runId={run.id} onClose={() => setShowLogs(false)} />}
    </Card>
  )
}

// ── Groups runs by calendar date and sums the metrics that matter for a
// "how many mails did we send each day" view. Dry runs are excluded from the
// sent total (they never actually emailed anyone) but still counted in
// runsCount for visibility. Pure function — no backend change needed, derived
// entirely from what /api/history already returns. ─────────────────────────
export function groupRunsByDate(runs) {
  const byDate = new Map()
  for (const run of runs) {
    const date = run.date || (run.timestamp ? run.timestamp.split('T')[0] : 'unknown')
    if (!byDate.has(date)) {
      byDate.set(date, { date, runsCount: 0, dryRunsCount: 0, totalSent: 0, totalScraped: 0, totalReal: 0, totalFailed: 0 })
    }
    const bucket = byDate.get(date)
    bucket.runsCount += 1
    if (run.dry_run) bucket.dryRunsCount += 1
    else bucket.totalSent += run.sent ?? 0
    bucket.totalScraped += run.scraped ?? 0
    bucket.totalReal += run.real ?? 0
    bucket.totalFailed += run.failed ?? 0
  }
  return [...byDate.values()].sort((a, b) => (a.date < b.date ? 1 : -1))
}

function formatDayLabel(dateStr) {
  if (dateStr === 'unknown') return 'Unknown date'
  const today = new Date().toISOString().split('T')[0]
  const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0]
  if (dateStr === today) return 'Today'
  if (dateStr === yesterday) return 'Yesterday'
  return new Date(dateStr).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
}

function DailyTotalsRow({ days, selectedDate, onSelect }) {
  if (days.length === 0) return null
  return (
    <div className="flex-shrink-0 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest flex items-center gap-1.5">
          <CalendarDays className="w-3.5 h-3.5" />
          Daily Totals
        </h3>
        {selectedDate && (
          <button onClick={() => onSelect(null)} className="text-xs text-primary hover:underline flex items-center gap-1">
            <X className="w-3 h-3" /> Clear filter
          </button>
        )}
      </div>
      <div className="flex gap-3 overflow-x-auto pb-1">
        {days.slice(0, 14).map(d => {
          const active = selectedDate === d.date
          return (
            <button
              key={d.date}
              onClick={() => onSelect(active ? null : d.date)}
              className={cn(
                'flex-shrink-0 text-left rounded-xl border px-4 py-3 min-w-[140px] transition-colors',
                active ? 'border-primary bg-primary/10' : 'border-border bg-card hover:border-primary/30'
              )}
            >
              <p className="text-xs text-muted-foreground font-medium mb-1">{formatDayLabel(d.date)}</p>
              <p className="text-xl font-bold text-emerald-400 tabular-nums">{d.totalSent}</p>
              <p className="text-xs text-muted-foreground">emails sent</p>
              <p className="text-xs text-muted-foreground/70 mt-1">
                {d.runsCount} run{d.runsCount !== 1 ? 's' : ''}{d.dryRunsCount > 0 ? ` (${d.dryRunsCount} dry)` : ''}
              </p>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default function HistoryPage() {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedDate, setSelectedDate] = useState(null)

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

  const dailyTotals = useMemo(() => groupRunsByDate(runs), [runs])
  const visibleRuns = selectedDate
    ? runs.filter(r => (r.date || (r.timestamp ? r.timestamp.split('T')[0] : 'unknown')) === selectedDate)
    : runs

  return (
    <div className="h-full flex flex-col overflow-hidden p-6 gap-4">
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-lg font-bold text-foreground">Pipeline History</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Daily totals below, full run-by-run history underneath — click "View Logs" for the full transcript, or a row for Brevo delivery stats
          </p>
        </div>
        <Button variant="outline" onClick={fetchHistory} disabled={loading} className="gap-2">
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Refresh
        </Button>
      </div>

      <DailyTotalsRow days={dailyTotals} selectedDate={selectedDate} onSelect={setSelectedDate} />

      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {loading && (
          <div className="flex items-center justify-center h-40">
            <Loader2 className="w-6 h-6 text-primary animate-spin" />
          </div>
        )}

        {!loading && visibleRuns.length === 0 && (
          <div className="flex flex-col items-center justify-center h-40 text-muted-foreground">
            <Inbox className="w-10 h-10 mb-3 opacity-50" />
            <p className="text-sm">{selectedDate ? 'No runs on this date' : 'No pipeline runs yet'}</p>
            {!selectedDate && <p className="text-xs mt-1">Run the pipeline from the Dashboard to see history here</p>}
          </div>
        )}

        {!loading && visibleRuns.map(run => (
          <RunCard key={run.id} run={run} />
        ))}
      </div>
    </div>
  )
}
