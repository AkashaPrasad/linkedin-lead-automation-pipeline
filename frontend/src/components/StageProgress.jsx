import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const STATUS_CONFIG = {
  waiting: { badge: 'bg-secondary text-muted-foreground border-transparent', label: 'Waiting' },
  running: { badge: 'bg-primary/15 text-primary border-primary/30', label: 'Running' },
  done: { badge: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', label: 'Done' },
  failed: { badge: 'bg-destructive/10 text-destructive border-destructive/20', label: 'Failed' },
}

function StageIcon({ status }) {
  if (status === 'done') return <CheckCircle2 className="w-4 h-4 text-white" />
  if (status === 'running') return <Loader2 className="w-4 h-4 text-white animate-spin" />
  if (status === 'failed') return <XCircle className="w-4 h-4 text-white" />
  return <Circle className="w-3.5 h-3.5 text-muted-foreground" />
}

export default function StageProgress({ stages }) {
  return (
    <Card className="border-border/80 bg-card h-full overflow-auto">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          Pipeline Stages
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {stages.map((stage, idx) => {
          const cfg = STATUS_CONFIG[stage.status] || STATUS_CONFIG.waiting
          const isRunning = stage.status === 'running'
          return (
            <div
              key={stage.id}
              className={cn(
                'flex items-start gap-3 p-3 rounded-lg transition-colors duration-200',
                isRunning ? 'bg-primary/5 ring-1 ring-primary/20' : 'hover:bg-secondary/60'
              )}
            >
              <div className="flex flex-col items-center flex-shrink-0">
                <div
                  className={cn(
                    'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors duration-200',
                    stage.status === 'done' && 'bg-emerald-500',
                    stage.status === 'running' && 'bg-primary',
                    stage.status === 'failed' && 'bg-destructive',
                    stage.status === 'waiting' && 'bg-secondary border border-border'
                  )}
                >
                  <StageIcon status={stage.status} />
                </div>
                {idx < stages.length - 1 && (
                  <div className={cn('w-px h-4 mt-1', stage.status === 'done' ? 'bg-emerald-500/30' : 'bg-border')} />
                )}
              </div>

              <div className="flex-1 min-w-0 pt-0.5">
                <div className="flex items-center justify-between gap-2">
                  <span className={cn('text-sm font-medium', isRunning ? 'text-primary' : 'text-foreground')}>
                    {stage.name}
                  </span>
                  <Badge variant="outline" className={cn('text-xs font-medium flex-shrink-0', cfg.badge)}>
                    {cfg.label}
                  </Badge>
                </div>
                {stage.metric && (
                  <p className="text-xs text-muted-foreground mt-1 truncate">{stage.metric}</p>
                )}
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
