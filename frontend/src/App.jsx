import { useState, useEffect, useRef, useCallback } from 'react'
import Dashboard from './components/Dashboard'
import TemplateEditor from './components/TemplateEditor'
import AdminPanel from './components/AdminPanel'
import HistoryPage from './components/HistoryPage'

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: '⚡' },
  { id: 'templates', label: 'Templates', icon: '✉' },
  { id: 'admin', label: 'Admin Panel', icon: '⚙' },
  { id: 'history', label: 'History', icon: '🕓' },
]

function Clock() {
  const [time, setTime] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <span className="text-text-secondary text-sm font-mono">
      {time.toLocaleTimeString('en-IN', { hour12: false })}
    </span>
  )
}

export default function App() {
  const [activeNav, setActiveNav] = useState('dashboard')
  const [isRunning, setIsRunning] = useState(false)
  const [stages, setStages] = useState(Array.from({ length: 9 }, (_, i) => ({
    id: i + 1,
    name: STAGE_NAMES[i],
    status: 'waiting',
    metric: '',
  })))
  const [stats, setStats] = useState({ scraped: 0, real: 0, enriched: 0, sent: 0 })
  const [leads, setLeads] = useState([])
  const [logs, setLogs] = useState([])
  const [error, setError] = useState(null)
  const [completionData, setCompletionData] = useState(null)
  const [sheetUrl, setSheetUrl] = useState('')
  const [isDryRun, setIsDryRun] = useState(false)
  const [isAutomated, setIsAutomated] = useState(false)
  const [checkpoint, setCheckpoint] = useState(null)
  const esRef = useRef(null)

  const fetchDryRunStatus = useCallback(() => {
    fetch('/api/admin/config')
      .then(r => r.json())
      .then(d => {
        setIsDryRun(d?.sending?.dry_run_mode === true)
        setIsAutomated(d?.automation?.enabled === true)
      })
      .catch(() => {})
  }, [])

  const fetchCheckpoint = useCallback(() => {
    fetch('/api/pipeline/checkpoint')
      .then(r => r.json())
      .then(d => setCheckpoint(d.exists ? d : null))
      .catch(() => setCheckpoint(null))
  }, [])

  useEffect(() => {
    fetch('/api/config/check').then(r => r.json()).then(d => setSheetUrl(d.sheet_url || '')).catch(() => {})
    fetch('/api/pipeline/status').then(r => r.json()).then(d => {
      if (d.is_running) setIsRunning(true)
    }).catch(() => {})
    fetchDryRunStatus()
    fetchCheckpoint()
  }, [])

  // Re-check dry run and checkpoint whenever navigating back to dashboard
  useEffect(() => {
    if (activeNav === 'dashboard') {
      fetchDryRunStatus()
      fetchCheckpoint()
    }
  }, [activeNav])

  // Allow Dashboard's "Go to Admin" link to navigate
  useEffect(() => {
    const handler = () => setActiveNav('admin')
    window.addEventListener('navigate-admin', handler)
    return () => window.removeEventListener('navigate-admin', handler)
  }, [])

  const addLog = useCallback((level, message) => {
    setLogs(prev => [...prev.slice(-499), { level, message, id: Date.now() + Math.random() }])
  }, [])

  const handleSSEEvent = useCallback((data) => {
    switch (data.event) {
      case 'stage_start':
        setStages(prev => prev.map(s =>
          s.id === data.stage ? { ...s, status: 'running', metric: data.message || '' } : s
        ))
        addLog('INFO', `Stage ${data.stage}: ${data.name} — ${data.message}`)
        break

      case 'stage_complete':
        setStages(prev => prev.map(s =>
          s.id === data.stage ? { ...s, status: 'done', metric: data.metric || '' } : s
        ))
        addLog('INFO', `✅ Stage ${data.stage} complete — ${data.metric}`)
        break

      case 'progress':
        addLog('INFO', data.message)
        break

      case 'lead':
        setLeads(prev => [data, ...prev].slice(0, 200))
        break

      case 'stats':
        setStats({ scraped: data.scraped, real: data.real, enriched: data.enriched, sent: data.sent })
        break

      case 'log':
        addLog(data.level || 'INFO', data.message)
        break

      case 'complete':
        setIsRunning(false)
        setCompletionData(data)
        setCheckpoint(null)
        addLog('INFO', `🎯 Pipeline complete — ${data.sent} sent, ${data.failed} failed, ${data.no_email} no email`)
        if (esRef.current) { esRef.current.close(); esRef.current = null }
        break

      case 'error':
        setIsRunning(false)
        setError(data.message)
        setStages(prev => prev.map(s =>
          s.status === 'running' ? { ...s, status: 'failed' } : s
        ))
        addLog('ERROR', `❌ Pipeline error: ${data.message}`)
        // Fetch checkpoint — it may have been saved before the error
        fetchCheckpoint()
        if (esRef.current) { esRef.current.close(); esRef.current = null }
        break

      case 'stopped':
        setIsRunning(false)
        setStages(prev => prev.map(s =>
          s.status === 'running' ? { ...s, status: 'waiting' } : s
        ))
        addLog('WARN', `🛑 ${data.message || 'Pipeline stopped'}`)
        fetchCheckpoint()
        if (esRef.current) { esRef.current.close(); esRef.current = null }
        break

      case 'heartbeat':
        break

      default:
        break
    }
  }, [addLog])

  const _connectSSE = useCallback(() => {
    if (esRef.current) esRef.current.close()
    const es = new EventSource('/api/pipeline/stream')
    esRef.current = es
    es.onmessage = (e) => {
      try { handleSSEEvent(JSON.parse(e.data)) } catch {}
    }
    es.onerror = () => {
      if (isRunning) addLog('WARN', 'SSE connection interrupted — reconnecting...')
    }
  }, [handleSSEEvent, addLog, isRunning])

  const _resetUI = useCallback((keepStagesDone = 0) => {
    setError(null)
    setCompletionData(null)
    setLeads([])
    setLogs([])
    setStats({ scraped: 0, real: 0, enriched: 0, sent: 0 })
    setStages(Array.from({ length: 9 }, (_, i) => ({
      id: i + 1,
      name: STAGE_NAMES[i],
      status: i < keepStagesDone ? 'done' : 'waiting',
      metric: i < keepStagesDone ? 'Completed (checkpoint)' : '',
    })))
  }, [])

  const resumePipeline = useCallback(async () => {
    const stagesDone = checkpoint?.stage_completed || 0
    _resetUI(stagesDone)
    setCheckpoint(null)

    try {
      const res = await fetch('/api/pipeline/resume', { method: 'POST' })
      if (!res.ok) {
        const body = await res.json()
        setError(body.detail || 'Failed to resume pipeline')
        return
      }
    } catch (e) {
      setError('Cannot reach the backend API from this deployment.')
      return
    }
    setIsRunning(true)
    _connectSSE()
  }, [checkpoint, _resetUI, _connectSSE])

  const startPipeline = useCallback(async () => {
    _resetUI(0)
    setCheckpoint(null)

    try {
      const res = await fetch('/api/pipeline/run', { method: 'POST' })
      if (!res.ok) {
        const body = await res.json()
        setError(body.detail || 'Failed to start pipeline')
        return
      }
    } catch (e) {
      setError('Cannot reach the backend API from this deployment.')
      return
    }

    setIsRunning(true)
    _connectSSE()
  }, [_resetUI, _connectSSE, handleSSEEvent])

  const promoteDryRun = useCallback(async (tabName) => {
    _resetUI(0)
    setCheckpoint(null)

    try {
      const res = await fetch('/api/pipeline/promote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tab_name: tabName }),
      })
      if (!res.ok) {
        const body = await res.json()
        setError(body.detail || 'Failed to start promote')
        return false
      }
    } catch (e) {
      setError('Cannot reach the backend API from this deployment.')
      return false
    }

    setIsRunning(true)
    _connectSSE()
    return true
  }, [_resetUI, _connectSSE])

  const stopPipeline = useCallback(async () => {
    try {
      const res = await fetch('/api/pipeline/stop', { method: 'POST' })
      if (!res.ok) {
        const body = await res.json()
        setError(body.detail || 'Failed to stop pipeline')
        return
      }
    } catch (e) {
      setError('Cannot reach the backend API from this deployment.')
      return
    }
    setIsRunning(false)
    addLog('WARN', '🛑 Stop requested...')
    if (esRef.current) { esRef.current.close(); esRef.current = null }
  }, [addLog])

  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary">
      {/* Sidebar */}
      <aside className="w-[220px] flex-shrink-0 bg-bg-secondary border-r border-border-color flex flex-col">
        <div className="px-5 py-6 border-b border-border-color">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full bg-purple-primary animate-pulse" />
            <span className="text-xs font-semibold text-purple-light tracking-widest uppercase">Decision</span>
          </div>
          <h1 className="text-base font-bold text-text-primary leading-tight">Pinnacle Pipeline</h1>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map(item => (
            <button
              key={item.id}
              onClick={() => setActiveNav(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeNav === item.id
                  ? 'bg-purple-primary/20 text-purple-light border border-purple-primary/30'
                  : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
              }`}
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="px-5 py-4 border-t border-border-color space-y-2">
          <div className={`flex items-center gap-2 text-xs ${isRunning ? 'text-green-accent' : 'text-text-muted'}`}>
            <div className={`w-1.5 h-1.5 rounded-full ${isRunning ? 'bg-green-accent animate-pulse' : 'bg-text-muted'}`} />
            {isRunning ? 'Pipeline running' : 'Ready'}
          </div>
          {isDryRun && (
            <div className="flex items-center gap-1.5 text-xs text-amber-accent">
              <span>⚠</span>
              <span className="font-semibold">DRY RUN ON</span>
            </div>
          )}
          {isAutomated && (
            <div className="flex items-center gap-1.5 text-xs text-green-accent">
              <span>⚡</span>
              <span className="font-semibold">AUTO SCHEDULE ON</span>
            </div>
          )}
        </div>
      </aside>

      {/* Main area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="flex items-center justify-between px-6 py-4 bg-bg-secondary border-b border-border-color flex-shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-text-primary">
              {activeNav === 'dashboard' ? 'Pipeline Dashboard' : activeNav === 'templates' ? 'Email Templates' : activeNav === 'admin' ? 'Admin Panel' : 'Run History'}
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <Clock />
            {isDryRun && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-accent/15 border border-amber-accent/40 text-amber-accent text-xs font-semibold">
                ⚠ DRY RUN
              </span>
            )}
            {isRunning && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-purple-primary/20 border border-purple-primary/30 text-purple-light text-xs font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-purple-light animate-pulse" />
                Running
              </span>
            )}
          </div>
        </header>

        {/* Error banner */}
        {error && (
          <div className="mx-6 mt-4 px-4 py-3 bg-red-accent/10 border border-red-accent/30 rounded-lg flex items-start gap-3">
            <span className="text-red-accent text-sm mt-0.5">⚠</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-red-accent">Pipeline Error</p>
              <p className="text-xs text-text-secondary mt-0.5">{error}</p>
            </div>
            <button onClick={() => setError(null)} className="text-text-muted hover:text-text-primary text-xs">✕</button>
          </div>
        )}

        {/* Content */}
        <main className="flex-1 overflow-hidden">
          {activeNav === 'dashboard' && (
            <Dashboard
              isRunning={isRunning}
              isDryRun={isDryRun}
              checkpoint={checkpoint}
              stages={stages}
              stats={stats}
              leads={leads}
              logs={logs}
              completionData={completionData}
              sheetUrl={sheetUrl}
              onRun={startPipeline}
              onResume={resumePipeline}
              onStop={stopPipeline}
              onPromote={promoteDryRun}
              onDismissCheckpoint={() => {
                fetch('/api/pipeline/checkpoint', { method: 'DELETE' }).catch(() => {})
                setCheckpoint(null)
              }}
              onDismissComplete={() => setCompletionData(null)}
              onViewHistory={() => setActiveNav('history')}
            />
          )}
          {activeNav === 'templates' && <TemplateEditor />}
          {activeNav === 'admin' && <AdminPanel />}
          {activeNav === 'history' && <HistoryPage />}
        </main>
      </div>
    </div>
  )
}

const STAGE_NAMES = [
  'Apify Scraper',
  'Deduplication',
  'GPT Filter',
  'AI Classify',
  'Google Sheets',
  'Apollo Enrichment',
  'Email Decision',
  'Email Sender',
  'Finalize Sheets',
]
