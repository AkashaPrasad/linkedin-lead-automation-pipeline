import { Play, Loader2, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export default function PipelineRunner({ isRunning, isDryRun, onRun }) {
  return (
    <Button
      onClick={onRun}
      disabled={isRunning}
      size="lg"
      className={cn(
        'gap-2 px-6 font-semibold shadow-lg transition-all active:scale-[0.97]',
        !isRunning && isDryRun && 'bg-amber-500 text-black hover:bg-amber-500/90',
        !isRunning && !isDryRun && 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-primary/20'
      )}
    >
      {isRunning ? (
        <>
          <Loader2 className="w-4 h-4 animate-spin" />
          {isDryRun ? 'Dry Running...' : 'Running...'}
        </>
      ) : isDryRun ? (
        <>
          <AlertTriangle className="w-4 h-4" />
          Run Dry Test
        </>
      ) : (
        <>
          <Play className="w-4 h-4 fill-current" />
          Run Pipeline
        </>
      )}
    </Button>
  )
}
