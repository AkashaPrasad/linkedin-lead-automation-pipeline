import { useState, useEffect } from 'react'
import { ArrowRight, Save, Target, ExternalLink, ScrollText, X, AlertTriangle } from 'lucide-react'
import StatsBar from './StatsBar'
import StageProgress from './StageProgress'
import LogConsole from './LogConsole'
import PipelineRunner from './PipelineRunner'
import BrevoStatsPanel from './BrevoStatsPanel'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

// ── Promote dry run to real send ───────────────────────────────────────────
function PromoteDryRunModal({ open, onClose, onPromote }) {
  const [tabs, setTabs] = useState([])
  const [selectedTab, setSelectedTab] = useState('')
  const [loadingTabs, setLoadingTabs] = useState(true)
  const [preview, setPreview] = useState(null)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState(null)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (!open) return
    fetch('/api/pipeline/promote/tabs')
      .then(r => r.json())
      .then(d => {
        const found = d.tabs || []
        setTabs(found)
        if (found.length) setSelectedTab(found[0])
        setLoadingTabs(false)
      })
      .catch(() => setLoadingTabs(false))
  }, [open])

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
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Promote Dry Run to Real Send</DialogTitle>
          <DialogDescription>Sends the exact leads already in a dry-run tab — no re-scraping</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label className="text-xs text-muted-foreground font-medium uppercase tracking-wide block mb-1.5">
              Dry-run tab
            </label>
            {loadingTabs ? (
              <p className="text-xs text-muted-foreground">Loading tabs...</p>
            ) : tabs.length === 0 ? (
              <p className="text-xs text-amber-400">No "[DRY]" tabs found in the sheet.</p>
            ) : (
              <Select value={selectedTab} onValueChange={(v) => { setSelectedTab(v); setPreview(null) }}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a tab" />
                </SelectTrigger>
                <SelectContent>
                  {tabs.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
          </div>

          {tabs.length > 0 && (
            <Button variant="outline" size="sm" onClick={checkTab} disabled={checking || !selectedTab}>
              {checking ? 'Checking...' : 'Check this tab'}
            </Button>
          )}

          {preview && (
            <div className="p-4 bg-secondary/50 border border-border rounded-xl space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Promotable leads</span>
                <span className="font-semibold text-foreground">{preview.promotable}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Already have an email</span>
                <span className="text-emerald-400">{preview.already_have_email}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Need Apollo enrichment</span>
                <span className="text-amber-400">{preview.need_apollo}</span>
              </div>
              {preview.promotable === 0 && (
                <p className="text-xs text-muted-foreground pt-1">Nothing eligible — either already promoted, or no REAL leads in this tab.</p>
              )}
            </div>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {preview && preview.promotable > 0 && (
            <p className="text-xs text-amber-400/90">
              This will send {preview.promotable} real emails via Brevo and write them into Master. Cannot be undone.
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 pt-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={send}
            disabled={!preview || preview.promotable === 0 || sending}
          >
            {sending ? 'Starting...' : preview ? `Send All ${preview.promotable} Leads` : 'Check tab first'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function CompletionModal({ data, sheetUrl, onDismiss, onViewHistory }) {
  const items = data ? [
    { label: 'Posts Scraped', value: data.scraped, color: 'text-primary' },
    { label: 'Real Leads', value: data.real, color: 'text-emerald-400' },
    { label: 'Emails Sent', value: data.sent, color: 'text-emerald-400' },
    { label: 'Failed', value: data.failed, color: 'text-destructive' },
    { label: 'No Email', value: data.no_email, color: 'text-amber-400' },
    { label: 'With Email', value: data.with_email, color: 'text-sky-400' },
  ] : []

  return (
    <Dialog open={!!data} onOpenChange={(v) => !v && onDismiss()}>
      <DialogContent className="max-w-md">
        <div className="text-center mb-2">
          <div className="mx-auto w-12 h-12 rounded-full bg-primary/15 flex items-center justify-center mb-3">
            <Target className="w-6 h-6 text-primary" />
          </div>
          <DialogHeader className="items-center">
            <DialogTitle>Pipeline Complete</DialogTitle>
            <DialogDescription>Finished in {data?.duration_min} minutes</DialogDescription>
          </DialogHeader>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-2">
          {items.map(item => (
            <div key={item.label} className="bg-secondary/60 rounded-lg p-3">
              <div className={`text-2xl font-bold ${item.color}`}>{item.value}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{item.label}</div>
            </div>
          ))}
        </div>

        <div className="flex gap-3">
          {sheetUrl && (
            <Button asChild variant="outline" className="flex-1 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 hover:text-emerald-400">
              <a href={sheetUrl} target="_blank" rel="noreferrer">
                <ExternalLink className="w-4 h-4" />
                View in Sheets
              </a>
            </Button>
          )}
          <Button
            variant="outline"
            className="flex-1 border-primary/30 text-primary hover:bg-primary/10 hover:text-primary"
            onClick={() => { onDismiss(); onViewHistory && onViewHistory() }}
          >
            View History
          </Button>
          <Button variant="secondary" onClick={onDismiss}>Close</Button>
        </div>
      </DialogContent>
    </Dialog>
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
    <Alert className="flex-shrink-0 border-sky-500/40 bg-sky-500/10">
      <Save className="h-4 w-4 text-sky-400" />
      <div className="flex-1 min-w-0 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <AlertTitle className="text-sky-400">Pipeline checkpoint found</AlertTitle>
          <AlertDescription className="text-sky-400/80">
            Last run completed through <span className="font-semibold">{stageLabel}</span>
            {ts && <span> at {ts}</span>}.{' '}
            {checkpoint.real_posts_count > 0 && (
              <span>{checkpoint.real_posts_count} real leads are ready — no need to re-scrape or re-classify.</span>
            )}
          </AlertDescription>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Button size="sm" className="bg-sky-500/20 border border-sky-500/40 text-sky-400 hover:bg-sky-500/30" onClick={onResume}>
            Resume from Stage {checkpoint.stage_completed + 1}
          </Button>
          <button onClick={onDismiss} title="Discard checkpoint and run fresh" className="text-muted-foreground hover:text-foreground">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </Alert>
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
        <Alert className="flex-shrink-0 border-amber-500/40 bg-amber-500/10">
          <AlertTriangle className="h-4 w-4 text-amber-400" />
          <div className="flex-1 min-w-0 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <AlertTitle className="text-amber-400">DRY RUN MODE IS ON</AlertTitle>
              <AlertDescription className="text-amber-400/80">
                The pipeline will run fully but <span className="font-semibold">no emails will be sent</span>. Leads are logged to a <span className="font-semibold">[DRY] tab</span> in Sheets — not the Master sheet.
              </AlertDescription>
            </div>
            <button
              onClick={() => window.dispatchEvent(new CustomEvent('navigate-admin'))}
              className="flex-shrink-0 text-xs text-amber-400 underline hover:no-underline flex items-center gap-1"
            >
              Go to Admin <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </Alert>
      )}

      {/* Header row */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-lg font-bold text-foreground">LinkedIn Lead Pipeline</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Scrape → Filter → Enrich → Send</p>
        </div>
        <div className="flex items-center gap-3">
          {!isRunning && (
            <Button variant="outline" onClick={() => setShowPromoteModal(true)} className="gap-2">
              <ArrowRight className="w-4 h-4" />
              Promote Dry Run
            </Button>
          )}
          <PipelineRunner isRunning={isRunning} isDryRun={isDryRun} onRun={onRun} />
          {isRunning && (
            <Button variant="destructive" onClick={onStop} className="gap-2">
              <span className="w-2.5 h-2.5 rounded-sm bg-current" />
              Stop
            </Button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="flex-shrink-0">
        <StatsBar stats={stats} />
      </div>

      {/* Main grid */}
      <div className={`flex-1 grid gap-4 min-h-0 ${showBrevoStats ? 'grid-cols-[300px_1fr]' : 'grid-cols-[300px_1fr]'}`}>
        <div className="min-h-0">
          <StageProgress stages={stages} />
        </div>

        {showBrevoStats ? (
          <div className="grid gap-4 min-h-0" style={{ gridTemplateRows: '1fr 280px' }}>
            <div className="min-h-0 overflow-hidden">
              <BrevoStatsPanel />
            </div>
            <div className="min-h-0">
              <LogConsole logs={logs} />
            </div>
          </div>
        ) : (
          <div className="min-h-0">
            <LogConsole logs={logs} />
          </div>
        )}
      </div>

      {/* Completion modal */}
      <CompletionModal
        data={completionData}
        sheetUrl={sheetUrl}
        onDismiss={onDismissComplete}
        onViewHistory={onViewHistory}
      />

      {/* Promote dry run modal */}
      <PromoteDryRunModal
        open={showPromoteModal}
        onClose={() => setShowPromoteModal(false)}
        onPromote={onPromote}
      />
    </div>
  )
}
