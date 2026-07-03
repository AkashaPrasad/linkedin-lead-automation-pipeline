import { useEffect, useRef, useState } from 'react'
import { Maximize2 } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

const LEVEL_COLORS = {
  INFO: 'text-muted-foreground',
  WARN: 'text-amber-400',
  WARNING: 'text-amber-400',
  ERROR: 'text-destructive',
  DEBUG: 'text-muted-foreground/60',
}

const LEVEL_PREFIXES = {
  INFO: 'INFO ',
  WARN: 'WARN ',
  WARNING: 'WARN ',
  ERROR: 'ERR  ',
  DEBUG: 'DBG  ',
}

function LogLines({ logs, textSize = 'text-xs' }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  if (logs.length === 0) {
    return <span className="text-muted-foreground/70">$ waiting for pipeline to start...</span>
  }

  return (
    <>
      {logs.map((log) => (
        <div key={log.id} className={cn('flex gap-3 leading-relaxed', textSize)}>
          <span className={cn('flex-shrink-0 opacity-60', LEVEL_COLORS[log.level] || 'text-muted-foreground')}>
            {LEVEL_PREFIXES[log.level] || 'LOG  '}
          </span>
          <span className={LEVEL_COLORS[log.level] || 'text-muted-foreground'}>
            {log.message}
          </span>
        </div>
      ))}
      <div ref={bottomRef} />
    </>
  )
}

export default function LogConsole({ logs }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="bg-[#0a0a0f] rounded-xl border border-border flex flex-col min-h-0 h-full">
      <div className="px-4 py-2.5 border-b border-border flex items-center gap-2 flex-shrink-0">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-destructive/50" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500/50" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/50" />
        </div>
        <span className="text-xs text-muted-foreground font-mono ml-2">pipeline.log</span>
        <span className="ml-auto text-xs text-muted-foreground">{logs.length} lines</span>
        <button
          onClick={() => setExpanded(true)}
          className="text-muted-foreground hover:text-foreground transition-colors"
          title="Expand full-screen"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
      </div>

      <ScrollArea className="flex-1 font-mono">
        <div className="p-4">
          <LogLines logs={logs} />
        </div>
      </ScrollArea>

      <Dialog open={expanded} onOpenChange={setExpanded}>
        <DialogContent className="max-w-4xl h-[85vh] flex flex-col p-0 gap-0 bg-[#0a0a0f] border-border">
          <DialogHeader className="px-6 py-4 border-b border-border flex-shrink-0">
            <DialogTitle className="text-foreground font-mono text-sm">pipeline.log — {logs.length} lines</DialogTitle>
          </DialogHeader>
          <ScrollArea className="flex-1 font-mono">
            <div className="p-6">
              <LogLines logs={logs} textSize="text-sm" />
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  )
}
