import { useState, useEffect } from 'react'
import StatsBar from './StatsBar'
import StageProgress from './StageProgress'
import LeadTable from './LeadTable'
import LogConsole from './LogConsole'
import PipelineRunner from './PipelineRunner'
import BrevoStatsPanel from './BrevoStatsPanel'

// ── Promote dry run to real send ───────────────────────────────────────────────
function PromoteDryRunModal({ onClose, onPromote }) {
  const [tabs, setTabs] = useState([])
  const [selectedTab, setSelectedTab] = useState('')
  const [loadingTabs, setLoadingTabs] = useState(true)
  const [preview, setPreview] = useState(null)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState(null)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    fetch('/api/pipeline/promote/tabs')
      .then(r => r.json())
      .then(d => {
        const found = d.tabs || []
        setTabs(found)
        if (found.length) setSelectedTab(found[0])
        setLoadingTabs(false)
      })
      .catch(() => setLoadingTabs(false))
  }, [])

  const checkTab = async () => {
    if (!selectedTab) return
    setChecking(true)
    setError(null)
    setPreview(null)
    try {
      const res = await fetch(`/api/pipeline/promote/preview?tab=${encodeURIComponent(selectedTab)}`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Could not read tab')
      setPreview(data)
    } catch (e) {
      setError(e.message)
    }
    setChecking(false)
  }

  const send = async () => {
    setSending(true)
    setError(null)
    const ok = await onPromote(selectedTab)
    setSending(false)
    if (ok) onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-bg-secondary border border-border-color rounded-2xl w-full max-w-lg overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-color">
          <div>
            <h3 className="text-base font-bold text-text-primary">Promote Dry Run to Real Send</h3>
            <p className="text-xs text-text-muted mt-0.5">Sends the exact leads already in a dry-run tab — no re-scraping</p>
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary transition-colors">
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="text-xs text-text-muted font-medium uppercase tracking-wide block mb-1.5">
              Dry-run tab
            </label>
            {loadingTabs ? (
              <p className="text-xs text-text-muted">Loading tabs...</p>
            ) : tabs.length === 0 ? (
              <p className="text-xs text-amber-accent">No "[DRY]" tabs found in the sheet.</p>
            ) : (
              <select
                value={selectedTab}
                onChange={e => { setSelectedTab(e.target.value); setPreview(null) }}
                className="w-full bg-bg-primary border border-border-color rounded-lg px-4 py-2.5 text-sm text-text-primary focus:outline-none focus:border-purple-primary/50 transition-colors"
              >
                {tabs.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            )}
          </div>

          {tabs.length > 0 && (
            <button
              onClick={checkTab}
              disabled={checking || !selectedTab}
              className="px-4 py-2 rounded-lg border border-border-color text-text-secondary text-sm hover:text-text-primary hover:border-purple-primary/30 transition-colors disabled:opacity-40"
            >
              {checking ? 'Checking...' : 'Check this tab'}
            </button>
          )}

          {preview && (
            <div className="p-4 bg-bg-primary border border-border-color rounded-xl space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-text-secondary">Promotable leads</span>
                <span className="font-semibold text-text-primary">{preview.promotable}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-text-secondary">Already have an email</span>
                <span className="text-green-accent">{preview.already_have_email}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-text-secondary">Need Apollo enrichment</span>
                <span className="text-amber-accent">{preview.need_apollo}</span>
              </div>
              {preview.promotable === 0 && (
                <p className="text-xs text-text-muted pt-1">Nothing eligible — either already promoted, or no REAL leads in this tab.</p>
              )}
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-accent/10 border border-red-accent/30 rounded-lg">
              <span className="text-red-accent mt-0.5">⚠</span>
              <p className="text-sm text-red-accent">{error}</p>
            </div>
          )}

          {preview && preview.promotable > 0 && (
            <p className="text-xs text-amber-accent/90">
              This will send {preview.promotable} real emails via Brevo and write them into Master. Cannot be undone.
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border-color">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-border-color text-text-secondary text-sm hover:text-text-primary transition-colors">
            Cancel
          </button>
          <button
            onClick={send}
            disabled={!preview || preview.promotable === 0 || sending}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${
              preview && preview.promotable > 0 && !sending
                ? 'bg-purple-primary text-white hover:bg-purple-primary/90'
                : 'bg-bg-tertiary text-text-muted cursor-not-allowed'
            }`}
          >
            {sending ? 'Starting...' : preview ? `Send All ${preview.promotable} Leads` : 'Check tab first'}
          </button>
        </div>
      </div>
    </div>
  )
}

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
  completionData, sheetUrl, onRun, onResume, onStop, onPromote, onDismissCheckpoint,
  onDismissComplete, onViewHistory,
}) {
  const showBrevoStats = !!completionData && !isRunning
  const [showPromoteModal, setShowPromoteModal] = useState(false)

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
        <div className="flex items-center gap-3">
          {!isRunning && (
            <button
              onClick={() => setShowPromoteModal(true)}
              className="flex items-center gap-2 px-5 py-3 rounded-xl font-semibold text-sm bg-bg-tertiary border border-border-color text-text-secondary hover:text-text-primary hover:border-purple-primary/30 active:scale-95 transition-all"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
              Promote Dry Run
            </button>
          )}
          <PipelineRunner isRunning={isRunning} isDryRun={isDryRun} onRun={onRun} />
          {isRunning && (
            <button
              onClick={onStop}
              className="flex items-center gap-2 px-5 py-3 rounded-xl font-semibold text-sm bg-red-accent/10 border border-red-accent/40 text-red-accent hover:bg-red-accent/20 active:scale-95 transition-all"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <rect x="5" y="5" width="14" height="14" rx="2" />
              </svg>
              Stop
            </button>
          )}
        </div>
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

      {/* Promote dry run modal */}
      {showPromoteModal && (
        <PromoteDryRunModal
          onClose={() => setShowPromoteModal(false)}
          onPromote={onPromote}
        />
      )}
    </div>
  )
}
