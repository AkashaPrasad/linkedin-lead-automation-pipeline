import StatsBar from './StatsBar'
import StageProgress from './StageProgress'
import LeadTable from './LeadTable'
import LogConsole from './LogConsole'
import PipelineRunner from './PipelineRunner'
import BrevoStatsPanel from './BrevoStatsPanel'

function CompletionModal({ data, sheetUrl, onDismiss, onViewHistory }) {
  if (!data) return null
  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-bg-secondary border border-border-color rounded-2xl p-8 max-w-md w-full purple-glow">
        <div className="text-center mb-6">
          <div className="text-5xl mb-3">🎯</div>
          <h2 className="text-xl font-bold text-text-primary">Pipeline Complete</h2>
          <p className="text-text-secondary text-sm mt-1">Finished in {data.duration_min} minutes</p>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-6">
          {[
            { label: 'Posts Scraped', value: data.scraped, color: 'text-purple-light' },
            { label: 'Real Leads', value: data.real, color: 'text-green-accent' },
            { label: 'Emails Sent', value: data.sent, color: 'text-green-accent' },
            { label: 'Failed', value: data.failed, color: 'text-red-accent' },
            { label: 'No Email', value: data.no_email, color: 'text-amber-accent' },
            { label: 'With Email', value: data.with_email, color: 'text-blue-400' },
          ].map(item => (
            <div key={item.label} className="bg-bg-tertiary rounded-lg p-3">
              <div className={`text-2xl font-bold ${item.color}`}>{item.value}</div>
              <div className="text-xs text-text-muted mt-0.5">{item.label}</div>
            </div>
          ))}
        </div>

        <div className="flex gap-3">
          {sheetUrl && (
            <a
              href={sheetUrl}
              target="_blank"
              rel="noreferrer"
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-green-accent/10 border border-green-accent/30 text-green-accent rounded-lg text-sm font-medium hover:bg-green-accent/20 transition-colors"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
              View in Sheets
            </a>
          )}
          <button
            onClick={() => { onDismiss(); onViewHistory && onViewHistory() }}
            className="flex-1 px-4 py-2.5 bg-purple-primary/10 border border-purple-primary/30 text-purple-light rounded-lg text-sm font-medium hover:bg-purple-primary/20 transition-colors"
          >
            View History
          </button>
          <button
            onClick={onDismiss}
            className="px-4 py-2.5 bg-bg-tertiary border border-border-color text-text-secondary rounded-lg text-sm font-medium hover:text-text-primary hover:bg-bg-tertiary/80 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

const STAGE_LABELS = [
  'Apify Scraper', 'Deduplication', 'AI Filter', 'AI Classify',
  'Google Sheets', 'Apollo Enrichment', 'Email Decision', 'Email Sender', 'Finalize Sheets',
]

function CheckpointBanner({ checkpoint, onResume, onDismiss }) {
  if (!checkpoint) return null
  const stageLabel = STAGE_LABELS[checkpoint.stage_completed - 1] || `Stage ${checkpoint.stage_completed}`
  const ts = checkpoint.timestamp
    ? new Date(checkpoint.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
    : ''
  return (
    <div className="flex-shrink-0 flex items-start gap-3 px-4 py-3 bg-blue-400/10 border border-blue-400/40 rounded-xl">
      <span className="text-xl flex-shrink-0 mt-0.5">💾</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-bold text-blue-400">Pipeline checkpoint found</p>
        <p className="text-xs text-blue-400/80 mt-0.5">
          Last run completed through <span className="font-semibold">{stageLabel}</span>
          {ts && <span> at {ts}</span>}.{' '}
          {checkpoint.real_posts_count > 0 && (
            <span>{checkpoint.real_posts_count} real leads are ready — no need to re-scrape or re-classify.</span>
          )}
        </p>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          onClick={onResume}
          className="px-3 py-1.5 bg-blue-400/20 border border-blue-400/40 text-blue-400 text-xs font-semibold rounded-lg hover:bg-blue-400/30 transition-colors"
        >
          Resume from Stage {checkpoint.stage_completed + 1}
        </button>
        <button
          onClick={onDismiss}
          className="text-text-muted hover:text-text-primary text-xs px-1"
          title="Discard checkpoint and run fresh"
        >
          ✕
        </button>
      </div>
    </div>
  )
}

export default function Dashboard({
  isRunning, isDryRun, checkpoint, stages, stats, leads, logs,
  completionData, sheetUrl, onRun, onResume, onDismissCheckpoint,
  onDismissComplete, onViewHistory,
}) {
  const showBrevoStats = !!completionData && !isRunning

  return (
    <div className="h-full flex flex-col overflow-hidden p-6 gap-4">
      {/* Checkpoint banner */}
      {checkpoint && !isRunning && (
        <CheckpointBanner checkpoint={checkpoint} onResume={onResume} onDismiss={onDismissCheckpoint} />
      )}

      {/* Dry run warning banner */}
      {isDryRun && (
        <div className="flex-shrink-0 flex items-center gap-3 px-4 py-3 bg-amber-accent/10 border border-amber-accent/40 rounded-xl">
          <span className="text-xl flex-shrink-0">⚠</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-amber-accent">DRY RUN MODE IS ON</p>
            <p className="text-xs text-amber-accent/80 mt-0.5">
              The pipeline will run fully but <span className="font-semibold">no emails will be sent</span>. Leads are logged to a <span className="font-semibold">[DRY] tab</span> in Sheets — not the Master sheet. Turn off Dry Run in Admin Panel → Email Sending to send for real.
            </p>
          </div>
          <a
            href="#"
            onClick={e => { e.preventDefault(); window.dispatchEvent(new CustomEvent('navigate-admin')) }}
            className="flex-shrink-0 text-xs text-amber-accent underline hover:no-underline"
          >
            Go to Admin →
          </a>
        </div>
      )}

      {/* Header row */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-lg font-bold text-text-primary">LinkedIn Lead Pipeline</h2>
          <p className="text-xs text-text-muted mt-0.5">Scrape → Filter → Enrich → Send</p>
        </div>
        <PipelineRunner isRunning={isRunning} isDryRun={isDryRun} onRun={onRun} />
      </div>

      {/* Stats */}
      <div className="flex-shrink-0">
        <StatsBar stats={stats} />
      </div>

      {/* Main grid */}
      <div className={`flex-1 grid gap-4 min-h-0 ${showBrevoStats ? 'grid-cols-[280px_1fr] grid-rows-[1fr_180px]' : 'grid-cols-[280px_1fr_1fr] grid-rows-[1fr_180px]'}`}>
        {/* Stage progress — spans both rows */}
        <div className="row-span-2 overflow-auto">
          <StageProgress stages={stages} />
        </div>

        {showBrevoStats ? (
          /* After completion: Brevo stats spanning the right side */
          <div className="overflow-hidden">
            <BrevoStatsPanel />
          </div>
        ) : (
          <>
            {/* While running / idle: Lead table + placeholder */}
            <div className="overflow-hidden">
              <LeadTable leads={leads} />
            </div>
            <div className="bg-bg-secondary rounded-xl border border-border-color flex items-center justify-center overflow-hidden">
              <div className="text-center text-text-muted">
                <div className="text-3xl mb-2">📊</div>
                <p className="text-xs">Stats appear after run</p>
              </div>
            </div>
          </>
        )}

        {/* Log console — always spans the right columns in row 2 */}
        <div className={`${showBrevoStats ? 'col-span-1' : 'col-span-2'} overflow-hidden`}>
          <LogConsole logs={logs} />
        </div>
      </div>

      {/* Completion modal */}
      <CompletionModal
        data={completionData}
        sheetUrl={sheetUrl}
        onDismiss={onDismissComplete}
        onViewHistory={onViewHistory}
      />
    </div>
  )
}
