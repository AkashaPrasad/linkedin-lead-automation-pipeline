const STATUS_CONFIG = {
  waiting: { dot: 'bg-text-muted', badge: 'bg-bg-tertiary text-text-muted', label: 'Waiting' },
  running: { dot: 'bg-purple-light stage-active', badge: 'bg-purple-primary/20 text-purple-light border border-purple-primary/30', label: 'Running' },
  done: { dot: 'bg-green-accent', badge: 'bg-green-accent/10 text-green-accent border border-green-accent/20', label: 'Done' },
  failed: { dot: 'bg-red-accent', badge: 'bg-red-accent/10 text-red-accent border border-red-accent/20', label: 'Failed' },
}

export default function StageProgress({ stages }) {
  return (
    <div className="bg-bg-secondary rounded-xl border border-border-color p-5">
      <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wide mb-5">Pipeline Stages</h3>
      <div className="space-y-1">
        {stages.map((stage, idx) => {
          const cfg = STATUS_CONFIG[stage.status] || STATUS_CONFIG.waiting
          const isRunning = stage.status === 'running'
          return (
            <div
              key={stage.id}
              className={`flex items-start gap-3 p-3 rounded-lg transition-all ${
                isRunning ? 'bg-purple-primary/5 purple-glow-ring' : 'hover:bg-bg-tertiary/50'
              }`}
            >
              {/* Stage number with line */}
              <div className="flex flex-col items-center flex-shrink-0">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                    stage.status === 'done'
                      ? 'bg-green-accent text-white'
                      : stage.status === 'running'
                      ? 'bg-purple-primary text-white'
                      : stage.status === 'failed'
                      ? 'bg-red-accent text-white'
                      : 'bg-bg-tertiary text-text-muted border border-border-color'
                  }`}
                >
                  {stage.status === 'done' ? '✓' : stage.id}
                </div>
                {idx < stages.length - 1 && (
                  <div className={`w-px h-4 mt-1 ${stage.status === 'done' ? 'bg-green-accent/30' : 'bg-border-color'}`} />
                )}
              </div>

              {/* Stage info */}
              <div className="flex-1 min-w-0 pt-0.5">
                <div className="flex items-center justify-between gap-2">
                  <span className={`text-sm font-medium ${isRunning ? 'text-purple-light' : 'text-text-primary'}`}>
                    {stage.name}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${cfg.badge}`}>
                    {isRunning ? (
                      <span className="flex items-center gap-1">
                        <span className="w-1 h-1 rounded-full bg-purple-light animate-ping inline-block" />
                        Running
                      </span>
                    ) : cfg.label}
                  </span>
                </div>
                {stage.metric && (
                  <p className="text-xs text-text-muted mt-1 truncate">{stage.metric}</p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
