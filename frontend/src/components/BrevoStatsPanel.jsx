import { useState, useEffect } from 'react'
import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from 'recharts'
import { Inbox, AlertTriangle, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ChartContainer, ChartTooltip, ChartTooltipContent } from '@/components/ui/chart'
import { cn } from '@/lib/utils'

function StatCard({ label, value, color = 'text-foreground', sub }) {
  return (
    <div className="bg-secondary/60 border border-border/60 rounded-xl p-3.5 flex flex-col gap-1">
      <div className={cn('text-xl font-bold tabular-nums', color)}>{value ?? '—'}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
      {sub != null && <div className="text-xs text-muted-foreground/80">{sub}</div>}
    </div>
  )
}

function pct(part, total) {
  if (!total || total === 0) return null
  return `${Math.round((part / total) * 100)}%`
}

// Sent = neutral total (informational), Delivered = "good" status, Bounced =
// "critical" status — colors follow status meaning, not arbitrary series order.
const CHART_CONFIG = {
  value: { label: 'Emails' },
  sent: { label: 'Sent', color: 'hsl(var(--muted-foreground))' },
  delivered: { label: 'Delivered', color: 'hsl(160.1 84.1% 39.4%)' },
  bounced: { label: 'Bounced', color: 'hsl(var(--destructive))' },
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
  const bounced = (stats?.hardBounces ?? 0) + (stats?.softBounces ?? 0)

  const chartData = stats ? [
    { name: 'Sent', value: stats.requests ?? 0, fill: 'var(--color-sent)' },
    { name: 'Delivered', value: stats.delivered ?? 0, fill: 'var(--color-delivered)' },
    { name: 'Bounced', value: bounced, fill: 'var(--color-bounced)' },
  ] : []

  return (
    <Card className="border-border/80 bg-card h-full flex flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between pb-3 space-y-0">
        <div className="flex items-center gap-2">
          <Inbox className="w-4 h-4 text-primary" />
          <CardTitle className="text-sm font-semibold">Brevo Email Stats</CardTitle>
          <span className="text-xs text-muted-foreground">— {displayDate}</span>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-auto space-y-5">
        {loading && (
          <div className="h-full flex items-center justify-center py-10">
            <Loader2 className="w-5 h-5 text-primary animate-spin" />
          </div>
        )}

        {error && (
          <div className="h-full flex items-center justify-center py-10">
            <div className="text-center text-muted-foreground max-w-[220px]">
              <AlertTriangle className="w-6 h-6 mx-auto mb-2 text-amber-400" />
              <p className="text-xs font-medium">Could not load Brevo stats</p>
              <p className="text-xs mt-1">{error}</p>
            </div>
          </div>
        )}

        {!loading && !error && stats && (
          <>
            <ChartContainer config={CHART_CONFIG} className="w-full h-[140px] aspect-auto">
              <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 24 }}>
                <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="name"
                  tickLine={false}
                  axisLine={false}
                  width={70}
                />
                <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                <Bar dataKey="value" radius={4}>
                  <LabelList dataKey="value" position="right" className="fill-foreground text-xs font-semibold" />
                </Bar>
              </BarChart>
            </ChartContainer>

            <div className="grid grid-cols-3 gap-3">
              <StatCard
                label="Delivery Rate"
                value={pct(stats.delivered, stats.requests) ?? '—'}
                color="text-emerald-400"
              />
              <StatCard
                label="Unique Opens"
                value={stats.uniqueOpens ?? 0}
                color="text-sky-400"
                sub={pct(stats.uniqueOpens, stats.delivered) ? `${pct(stats.uniqueOpens, stats.delivered)} open rate` : null}
              />
              <StatCard
                label="Unique Clicks"
                value={stats.uniqueClicks ?? 0}
                color="text-sky-400"
                sub={pct(stats.uniqueClicks, stats.delivered) ? `${pct(stats.uniqueClicks, stats.delivered)} click rate` : null}
              />
              <StatCard
                label="Unsubscribed"
                value={stats.unsubscribed ?? 0}
                color={stats.unsubscribed > 0 ? 'text-amber-400' : 'text-muted-foreground'}
              />
              <StatCard
                label="Spam Reports"
                value={stats.spamReports ?? 0}
                color={stats.spamReports > 0 ? 'text-destructive' : 'text-muted-foreground'}
              />
              <StatCard
                label="Blocked / Invalid"
                value={(stats.blocked ?? 0) + (stats.invalid ?? 0)}
                color={(stats.blocked ?? 0) + (stats.invalid ?? 0) > 0 ? 'text-amber-400' : 'text-muted-foreground'}
              />
            </div>
          </>
        )}

        {!loading && !error && !stats && (
          <div className="h-full flex items-center justify-center text-muted-foreground text-xs py-10">
            No data available
          </div>
        )}
      </CardContent>
    </Card>
  )
}
