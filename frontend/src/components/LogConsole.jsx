import { useEffect, useRef } from 'react'

const LEVEL_COLORS = {
  INFO: 'text-text-secondary',
  WARN: 'text-amber-accent',
  WARNING: 'text-amber-accent',
  ERROR: 'text-red-accent',
  DEBUG: 'text-text-muted',
}

const LEVEL_PREFIXES = {
  INFO: 'INFO ',
  WARN: 'WARN ',
  WARNING: 'WARN ',
  ERROR: 'ERR  ',
  DEBUG: 'DBG  ',
}

export default function LogConsole({ logs }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="bg-[#0D0D14] rounded-xl border border-border-color flex flex-col min-h-0">
      <div className="px-4 py-2.5 border-b border-border-color flex items-center gap-2 flex-shrink-0">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-accent/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-accent/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-green-accent/60" />
        </div>
        <span className="text-xs text-text-muted font-mono ml-2">pipeline.log</span>
        <span className="ml-auto text-xs text-text-muted">{logs.length} lines</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed">
        {logs.length === 0 ? (
          <span className="text-text-muted">$ waiting for pipeline to start...</span>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="flex gap-3">
              <span className={`flex-shrink-0 ${LEVEL_COLORS[log.level] || 'text-text-muted'} opacity-60`}>
                {LEVEL_PREFIXES[log.level] || 'LOG  '}
              </span>
              <span className={LEVEL_COLORS[log.level] || 'text-text-secondary'}>
                {log.message}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
