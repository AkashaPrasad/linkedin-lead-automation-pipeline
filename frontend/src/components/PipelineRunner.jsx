export default function PipelineRunner({ isRunning, isDryRun, onRun }) {
  return (
    <button
      onClick={onRun}
      disabled={isRunning}
      className={`
        flex items-center gap-3 px-6 py-3 rounded-xl font-semibold text-sm transition-all
        ${isRunning
          ? 'bg-bg-tertiary text-text-muted cursor-not-allowed border border-border-color'
          : isDryRun
          ? 'bg-gradient-to-r from-amber-accent/80 to-amber-accent text-black hover:opacity-90 active:scale-95'
          : 'bg-gradient-to-r from-purple-primary to-purple-light text-white hover:opacity-90 active:scale-95 purple-glow'
        }
      `}
    >
      {isRunning ? (
        <>
          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {isDryRun ? 'Dry Running...' : 'Running...'}
        </>
      ) : isDryRun ? (
        <>
          <span className="text-base">⚠</span>
          Run Dry Test
        </>
      ) : (
        <>
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polygon points="5 3 19 12 5 21 5 3" fill="currentColor" />
          </svg>
          Run Pipeline
        </>
      )}
    </button>
  )
}
