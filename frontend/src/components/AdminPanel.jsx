import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import {
  Folder, FolderOpen, FolderPlus, X, Loader2, KeyRound, CheckCircle2,
  AlertTriangle, MousePointerClick, Zap, Clock as ClockIcon, Save,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogFooter,
  AlertDialogTitle, AlertDialogDescription, AlertDialogAction, AlertDialogCancel,
} from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'

const TABS = ['Scraping', 'AI Filtering', 'Enrichment', 'Email Sending', 'Automation']

// ── Reusable UI pieces ──────────────────────────────────────────────────────

function SectionLabel({ children }) {
  return <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3">{children}</h4>
}

function Field({ label, hint, children }) {
  return (
    <div className="space-y-1.5">
      <div>
        <Label className="text-sm font-medium text-foreground">{label}</Label>
        {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
      </div>
      {children}
    </div>
  )
}

function NumberInput({ value, onChange, min = 0, max = 99999, step = 1 }) {
  const [raw, setRaw] = useState(String(value))

  useEffect(() => {
    if (Number(raw) !== value) setRaw(String(value))
  }, [value])

  const commit = (str) => {
    const trimmed = str.trim()
    let num = trimmed === '' ? min : Number(trimmed)
    if (Number.isNaN(num)) num = min
    num = Math.min(max, Math.max(min, num))
    setRaw(String(num))
    onChange(num)
  }

  return (
    <Input
      type="number"
      value={raw}
      onChange={e => {
        const v = e.target.value
        setRaw(v)
        const num = Number(v)
        if (v.trim() !== '' && !Number.isNaN(num)) onChange(num)
      }}
      onBlur={e => commit(e.target.value)}
      min={min}
      max={max}
      step={step}
    />
  )
}

function SelectInput({ value, onChange, options }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map(o => (
          <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function Toggle({ value, onChange, label, hint }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-medium text-foreground">{label}</p>
        {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
      </div>
      <Switch checked={value} onCheckedChange={onChange} className="flex-shrink-0" />
    </div>
  )
}

// ── Editable list (like Apify keyword UI) ───────────────────────────────────
function EditableList({ items, onChange, placeholder = 'Add item...', addLabel = 'Add' }) {
  const [newItem, setNewItem] = useState('')

  const add = () => {
    const trimmed = newItem.trim()
    if (trimmed && !items.includes(trimmed)) {
      onChange([...items, trimmed])
      setNewItem('')
    }
  }

  const remove = (i) => onChange(items.filter((_, idx) => idx !== i))

  const handleKey = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); add() }
  }

  return (
    <div className="space-y-2">
      <div className="space-y-1.5">
        {items.map((item, i) => (
          <div
            key={i}
            className="flex items-center gap-2 bg-background border border-border rounded-lg px-3 py-2 group"
          >
            <span className="w-6 h-6 rounded-md bg-primary/10 text-primary text-xs font-bold flex items-center justify-center flex-shrink-0">
              {i + 1}
            </span>
            <span className="flex-1 text-sm text-foreground font-mono">{item}</span>
            <button
              onClick={() => remove(i)}
              className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors opacity-0 group-hover:opacity-100"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-xs text-muted-foreground italic px-1">No items — add one below</p>
        )}
      </div>

      <div className="flex gap-2">
        <Input
          value={newItem}
          onChange={e => setNewItem(e.target.value)}
          onKeyDown={handleKey}
          placeholder={placeholder}
          className="flex-1"
        />
        <Button variant="outline" onClick={add} disabled={!newItem.trim()}>
          {addLabel}
        </Button>
      </div>
    </div>
  )
}

// ── Query folder manager ─────────────────────────────────────────────────────
// Proper folder CRUD: "+ New Folder" always creates a BLANK set and switches to
// it immediately — no more inheriting whatever the previous folder's list held.
function QueryFolderManager({ cfg, onChange }) {
  const s = cfg.scraping || {}
  const a = cfg.automation || {}
  const querySets = s.query_sets || {}
  const activeSet = s.active_query_set || ''
  const setNames = Object.keys(querySets)

  const setMany = (patch) => onChange({ ...cfg, scraping: { ...s, ...patch } })

  const [newFolderOpen, setNewFolderOpen] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [renamingName, setRenamingName] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleteTarget, setDeleteTarget] = useState(null)

  const selectSet = (name) => {
    setMany({ active_query_set: name, search_queries: [...(querySets[name] || [])] })
  }

  const createFolder = () => {
    const trimmed = newFolderName.trim()
    if (!trimmed || querySets[trimmed]) return
    setMany({
      query_sets: { ...querySets, [trimmed]: [] },
      active_query_set: trimmed,
      search_queries: [],
    })
    setNewFolderName('')
    setNewFolderOpen(false)
    toast.success(`Folder "${trimmed}" created — add queries below`)
  }

  // Automation's per-time-slot folder assignments (Admin Panel → Automation)
  // reference folders by name — keep them in sync so a rename/delete here
  // never leaves a schedule silently pointing at a name that no longer
  // exists (the backend already falls back safely either way, but this
  // avoids the confusing dangling reference in the UI).
  const remapTimeQuerySets = (oldName, newNameOrNull) => {
    const map = a.time_query_sets || {}
    if (!Object.values(map).includes(oldName)) return null
    const next = {}
    for (const [time, folder] of Object.entries(map)) {
      if (folder === oldName) {
        if (newNameOrNull) next[time] = newNameOrNull
        // else: drop the entry entirely -> falls back to Default
      } else {
        next[time] = folder
      }
    }
    return next
  }

  const renameFolder = (oldName) => {
    const trimmed = renameValue.trim()
    if (!trimmed || trimmed === oldName) { setRenamingName(null); return }
    if (querySets[trimmed]) { toast.error(`A folder named "${trimmed}" already exists`); return }
    const next = { ...querySets }
    const queries = next[oldName] || []
    delete next[oldName]
    next[trimmed] = queries
    const isActive = activeSet === oldName
    const remappedTimeQuerySets = remapTimeQuerySets(oldName, trimmed)
    onChange({
      ...cfg,
      scraping: {
        ...s,
        query_sets: next,
        active_query_set: isActive ? trimmed : activeSet,
        ...(isActive ? { search_queries: [...queries] } : {}),
      },
      ...(remappedTimeQuerySets ? { automation: { ...a, time_query_sets: remappedTimeQuerySets } } : {}),
    })
    setRenamingName(null)
  }

  const deleteSet = (name) => {
    const next = { ...querySets }
    delete next[name]
    const remaining = Object.keys(next)
    const fallback = remaining[0] || ''
    const remappedTimeQuerySets = remapTimeQuerySets(name, null)
    onChange({
      ...cfg,
      scraping: activeSet === name
        ? { ...s, query_sets: next, active_query_set: fallback, search_queries: [...(next[fallback] || [])] }
        : { ...s, query_sets: next },
      ...(remappedTimeQuerySets ? { automation: { ...a, time_query_sets: remappedTimeQuerySets } } : {}),
    })
    setDeleteTarget(null)
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        {setNames.map(name => (
          <div
            key={name}
            className={cn(
              'group flex items-center gap-1 rounded-lg border pl-3 pr-1.5 py-1.5 transition-colors',
              name === activeSet
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-background text-muted-foreground hover:border-primary/40'
            )}
          >
            {renamingName === name ? (
              <input
                autoFocus
                value={renameValue}
                onChange={e => setRenameValue(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') renameFolder(name)
                  if (e.key === 'Escape') setRenamingName(null)
                }}
                onBlur={() => renameFolder(name)}
                className="bg-transparent text-sm font-medium outline-none w-28"
              />
            ) : (
              <button
                onClick={() => selectSet(name)}
                onDoubleClick={() => { setRenamingName(name); setRenameValue(name) }}
                className="text-sm font-medium flex items-center gap-1.5 py-0.5"
                title="Click to select, double-click to rename"
              >
                {name === activeSet ? <FolderOpen className="w-3.5 h-3.5" /> : <Folder className="w-3.5 h-3.5" />}
                {name}
              </button>
            )}
            <button
              onClick={() => setDeleteTarget(name)}
              title={`Delete ${name}`}
              className="w-5 h-5 rounded flex items-center justify-center text-muted-foreground hover:text-destructive transition-colors opacity-0 group-hover:opacity-100 flex-shrink-0"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        ))}
        {setNames.length === 0 && (
          <p className="text-xs text-muted-foreground italic px-1">No saved folders yet — create one</p>
        )}
        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setNewFolderOpen(true)}>
          <FolderPlus className="w-3.5 h-3.5" />
          New Folder
        </Button>
      </div>

      <Dialog open={newFolderOpen} onOpenChange={setNewFolderOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>New search query folder</DialogTitle>
            <DialogDescription>Creates a blank folder — add your queries into it right after, nothing is inherited.</DialogDescription>
          </DialogHeader>
          <Input
            autoFocus
            value={newFolderName}
            onChange={e => setNewFolderName(e.target.value)}
            placeholder="e.g. test-7"
            onKeyDown={e => e.key === 'Enter' && createFolder()}
          />
          {querySets[newFolderName.trim()] && (
            <p className="text-xs text-destructive">A folder with this name already exists</p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setNewFolderOpen(false)}>Cancel</Button>
            <Button onClick={createFolder} disabled={!newFolderName.trim() || !!querySets[newFolderName.trim()]}>
              Create
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete "{deleteTarget}"?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the folder and its saved queries once you click Save Changes. This can't be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteSet(deleteTarget)}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

// ── LinkedIn cookie manager ───────────────────────────────────────────────────
function LinkedInCookieManager() {
  const [status, setStatus] = useState(null)
  const [cookieInput, setCookieInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveStatus, setSaveStatus] = useState(null)

  const loadStatus = () => {
    fetch('/api/linkedin-cookie/status')
      .then(r => r.json())
      .then(setStatus)
      .catch(() => {})
  }

  useEffect(() => { loadStatus() }, [])

  const updateCookie = async () => {
    const trimmed = cookieInput.trim()
    if (!trimmed) return
    let parsed
    try {
      parsed = JSON.parse(trimmed)
    } catch {
      setSaveStatus('invalid-json')
      return
    }
    if (!Array.isArray(parsed) || parsed.length === 0) {
      setSaveStatus('invalid-format')
      return
    }
    setSaving(true)
    setSaveStatus(null)
    try {
      const res = await fetch('/api/linkedin-cookie', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cookie: trimmed }),
      })
      if (!res.ok) throw new Error('Save failed')
      setCookieInput('')
      setSaveStatus('saved')
      loadStatus()
      setTimeout(() => setSaveStatus(null), 3000)
    } catch (e) {
      setSaveStatus('error')
    }
    setSaving(false)
  }

  return (
    <div className="p-4 bg-background border border-border rounded-xl space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-foreground flex items-center gap-2">
          <KeyRound className="w-4 h-4 text-muted-foreground" />
          LinkedIn Session Cookies
        </p>
        {status?.configured ? (
          <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-400 gap-1">
            <CheckCircle2 className="w-3 h-3" /> configured ({status.preview})
          </Badge>
        ) : (
          <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-400">not configured</Badge>
        )}
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">
        The scraper actor needs your FULL LinkedIn session, not just one cookie. Install the{' '}
        <strong className="text-foreground">Cookie-Editor</strong> browser extension, log into
        LinkedIn, click the extension icon, choose <strong className="text-foreground">Export → Export as JSON</strong>,
        and paste the entire JSON array below (it will contain li_at, JSESSIONID, and several others —
        that's expected). A single li_at value alone will be rejected as "invalid cookies". This is
        stored only in the backend's local .env file, never committed to git.
      </p>
      <div className="space-y-2">
        <Textarea
          value={cookieInput}
          onChange={e => setCookieInput(e.target.value)}
          placeholder='Paste the full Cookie-Editor JSON export, e.g. [{"name":"li_at","value":"...","domain":".linkedin.com",...}, {"name":"JSESSIONID","value":"...",...}, ...]'
          autoComplete="off"
          rows={5}
          className="font-mono text-xs resize-y"
        />
        <Button onClick={updateCookie} disabled={!cookieInput.trim() || saving}>
          {saving ? 'Saving...' : 'Update Cookies'}
        </Button>
      </div>
      {saveStatus === 'saved' && <p className="text-xs text-emerald-400 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Cookies updated</p>}
      {saveStatus === 'error' && <p className="text-xs text-destructive">Failed to save cookies</p>}
      {saveStatus === 'invalid-json' && <p className="text-xs text-destructive">Not valid JSON — make sure you pasted the full export, not partial text.</p>}
      {saveStatus === 'invalid-format' && <p className="text-xs text-destructive">Must be a JSON array of cookie objects (Cookie-Editor's export format), not a single value.</p>}
    </div>
  )
}

// ── Tab panels ────────────────────────────────────────────────────────────────

function ScrapingTab({ cfg, onChange }) {
  const s = cfg.scraping || {}
  const set = (key, val) => onChange({ ...cfg, scraping: { ...s, [key]: val } })
  const setMany = (patch) => onChange({ ...cfg, scraping: { ...s, ...patch } })
  const flt = cfg.filtering || {}
  const setF = (key, val) => onChange({ ...cfg, filtering: { ...flt, [key]: val } })

  // Edits to the active folder's query list are mirrored into query_sets
  // immediately (in-session) — no separate "Update" step needed. The global
  // Save Changes button is still what actually reaches the backend.
  const setSearchQueries = (v) => {
    const patch = { search_queries: v }
    if (s.active_query_set && s.query_sets?.[s.active_query_set] !== undefined) {
      patch.query_sets = { ...(s.query_sets || {}), [s.active_query_set]: v }
    }
    setMany(patch)
  }

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <SectionLabel>Search Query Folders</SectionLabel>
        <Field
          label="Folders"
          hint="Organize keyword lists into folders and switch between them. New Folder starts blank — add queries below, they save into that folder automatically."
        >
          <QueryFolderManager cfg={cfg} onChange={onChange} />
        </Field>
      </div>

      <div className="space-y-4">
        <SectionLabel>
          Search Keywords{s.active_query_set && (
            <span className="text-muted-foreground font-normal normal-case tracking-normal"> — editing "{s.active_query_set}"</span>
          )}
        </SectionLabel>
        <Field label="Search Queries" hint="LinkedIn posts matching any of these keywords will be scraped.">
          <EditableList
            items={s.search_queries || []}
            onChange={setSearchQueries}
            placeholder="Add a search keyword or phrase..."
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-4">
          <SectionLabel>Post Limits</SectionLabel>
          <Field label="Max Posts Per Keyword" hint="How many posts to scrape for each search query (max 200)">
            <NumberInput value={s.max_posts_per_query || 50} onChange={v => set('max_posts_per_query', v)} min={5} max={200} step={5} />
          </Field>
          <Field label="Total Post Cap" hint="Hard limit on total posts across all keywords per run">
            <NumberInput value={s.total_post_cap || 500} onChange={v => set('total_post_cap', v)} min={50} max={2000} step={50} />
          </Field>
          <Field label="Minimum Post Length (chars)" hint="Skip posts shorter than this — very short posts are usually low quality">
            <NumberInput value={flt.min_post_length ?? 50} onChange={v => setF('min_post_length', v)} min={0} max={500} step={10} />
          </Field>
        </div>

        <div className="space-y-4">
          <SectionLabel>Post Filters</SectionLabel>
          <Field label="Posted Within" hint="Only scrape posts published within this timeframe">
            <SelectInput
              value={s.posted_limit || 'month'}
              onChange={v => set('posted_limit', v)}
              options={[
                { value: 'any', label: 'Any time' },
                { value: '1h', label: 'Past 1 hour' },
                { value: '24h', label: 'Past 24 hours' },
                { value: '48h', label: 'Past 48 hours' },
                { value: 'week', label: 'Past week' },
                { value: 'month', label: 'Past month' },
                { value: '3months', label: 'Past 3 months' },
                { value: '6months', label: 'Past 6 months' },
                { value: 'year', label: 'Past year' },
              ]}
            />
          </Field>
          <Field label="Sort By" hint="How Apify orders results within each query">
            <SelectInput
              value={s.sort_by || 'date'}
              onChange={v => set('sort_by', v)}
              options={[
                { value: 'date', label: 'Most recent' },
                { value: 'relevance', label: 'Most relevant' },
              ]}
            />
          </Field>
        </div>
      </div>

      <div className="space-y-4">
        <SectionLabel>Cookie-Authenticated Scraping</SectionLabel>
        <Toggle
          value={s.use_cookie_actor ?? false}
          onChange={v => set('use_cookie_actor', v)}
          label="Scrape with LinkedIn cookie"
          hint="Off: uses the default actor (no login, broader but noisier results). On: uses an authenticated actor with your LinkedIn session cookie below — required before enabling this."
        />
        <LinkedInCookieManager />
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-4">
          <SectionLabel>Author Filters (LinkedIn IDs)</SectionLabel>
          <Field
            label="Industry IDs"
            hint="Type or paste the industry name exactly as LinkedIn shows it (e.g. Marketing and Advertising, Consumer Goods, Real Estate). You can also use numeric IDs."
          >
            <EditableList
              items={s.author_industry_ids || []}
              onChange={v => set('author_industry_ids', v)}
              placeholder="e.g. Marketing and Advertising"
            />
          </Field>
        </div>
        <div className="space-y-4">
          <SectionLabel>Geo Filters (Optional)</SectionLabel>
          <Field
            label="Geo IDs"
            hint="LinkedIn geo IDs to limit author location. India = 102713980. Leave empty for worldwide."
          >
            <EditableList
              items={s.author_geo_ids || []}
              onChange={v => set('author_geo_ids', v)}
              placeholder="e.g. 102713980 (India)"
            />
          </Field>
        </div>
      </div>
    </div>
  )
}

function FilteringTab({ cfg, onChange }) {
  const f = cfg.filtering || {}
  const set = (key, val) => onChange({ ...cfg, filtering: { ...f, [key]: val } })

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <SectionLabel>AI Lead Filter (Stage 3)</SectionLabel>
        <div className="p-4 bg-background border border-border rounded-xl space-y-4">
          <Toggle
            value={f.gpt_filter_enabled ?? true}
            onChange={v => set('gpt_filter_enabled', v)}
            label="Enable GPT Lead Filter"
            hint="Uses Gemini/GPT to remove false leads (freelancers, job seekers, agency self-promotion). Disabling passes ALL scraped posts as real leads."
          />
          <Toggle
            value={f.only_posts_with_email ?? false}
            onChange={v => set('only_posts_with_email', v)}
            label="Only process posts containing an email"
            hint="Skip Apollo enrichment entirely — only proceed with leads whose posts explicitly include an email address"
          />
        </div>
      </div>

      <div className="space-y-4">
        <SectionLabel>Keyword Exclusions</SectionLabel>
        <Field
          label="Excluded Keywords"
          hint="Posts containing any of these words (case-insensitive) are silently skipped before AI filtering. Useful to filter out competitor agency names or irrelevant industries."
        >
          <EditableList
            items={f.excluded_keywords || []}
            onChange={v => set('excluded_keywords', v)}
            placeholder="e.g. PR agency, event management..."
          />
        </Field>
      </div>
    </div>
  )
}

function EnrichmentTab({ cfg, onChange }) {
  const e = cfg.enrichment || {}
  const set = (key, val) => onChange({ ...cfg, enrichment: { ...e, [key]: val } })
  const [apolloPlan, setApolloP] = useState(null)

  useEffect(() => {
    fetch('/api/apollo/plan-check')
      .then(r => r.json())
      .then(setApolloP)
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-8">
      {apolloPlan && !apolloPlan.accessible && (
        <Alert className="border-amber-500/40 bg-amber-500/10">
          <AlertTriangle className="h-4 w-4 text-amber-400" />
          <AlertTitle className="text-amber-400">Apollo Email Enrichment Not Available</AlertTitle>
          <AlertDescription className="text-amber-400/80 space-y-2">
            <p>{apolloPlan.reason}. This means leads without an email in their post will be marked <strong>NO_EMAIL</strong> and won't receive your outreach.</p>
            <p>
              To fix: upgrade to <strong>Apollo Starter ($49/month)</strong> — includes 300 email lookups/month.{' '}
              <a href="https://app.apollo.io/settings/plans" target="_blank" rel="noreferrer" className="underline hover:no-underline">
                Upgrade Apollo plan ↗
              </a>
            </p>
            <p className="text-muted-foreground">
              Alternative for now: use the <strong>Only posts with email</strong> toggle in AI Filtering tab.
            </p>
          </AlertDescription>
        </Alert>
      )}
      {apolloPlan?.accessible && (
        <Alert className="border-emerald-500/30 bg-emerald-500/10">
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          <AlertDescription className="text-emerald-400 font-medium">
            Apollo email enrichment is active and working on your plan.
          </AlertDescription>
        </Alert>
      )}

      <div className="space-y-4">
        <SectionLabel>Apollo.io Enrichment (Stage 6)</SectionLabel>
        <div className="p-4 bg-background border border-border rounded-xl space-y-4">
          <Toggle
            value={e.apollo_enabled ?? true}
            onChange={v => set('apollo_enabled', v)}
            label="Enable Apollo Email Enrichment"
            hint="Look up missing emails for real leads via Apollo.io. Disable if you've hit your Apollo monthly limit."
          />
        </div>
      </div>

      <div className="space-y-4">
        <SectionLabel>Enrichment Limits</SectionLabel>
        <Field label="Max Enrichment Lookups Per Run" hint="Apollo free plan gives limited lookups/month. Cap this to avoid burning through your quota in one run.">
          <NumberInput value={e.max_enrichment_per_run || 100} onChange={v => set('max_enrichment_per_run', v)} min={10} max={500} step={10} />
        </Field>
      </div>

      <div className="p-4 bg-primary/5 border border-primary/20 rounded-xl">
        <p className="text-xs text-primary font-medium mb-1">Apollo Quota Tip</p>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Apollo free plan: 50 email credits/month. Paid plans start at $49/month for 300 credits.
        </p>
      </div>
    </div>
  )
}

function SendingTab({ cfg, onChange }) {
  const s = cfg.sending || {}
  const set = (key, val) => onChange({ ...cfg, sending: { ...s, [key]: val } })

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <SectionLabel>Send Controls</SectionLabel>
        <div className="p-4 bg-background border border-border rounded-xl space-y-4">
          <Toggle
            value={s.dry_run_mode ?? false}
            onChange={v => set('dry_run_mode', v)}
            label="Dry Run Mode"
            hint="Simulate the full pipeline without actually sending any emails. All stages run normally — sends are logged as DRY_RUN in Sheets. Use to test setup."
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-4">
          <SectionLabel>Email Limits</SectionLabel>
          <Field label="Daily Email Cap" hint="Maximum emails to send per pipeline run (Brevo free = 300/day)">
            <NumberInput value={s.daily_email_cap || 100} onChange={v => set('daily_email_cap', v)} min={1} max={300} step={10} />
          </Field>
          <Field label="Delay Between Sends (seconds)" hint="Pause between each email send — avoids rate limits and looks more human">
            <NumberInput value={s.email_send_delay_seconds || 2} onChange={v => set('email_send_delay_seconds', v)} min={1} max={30} />
          </Field>
        </div>

        <div className="space-y-4">
          <SectionLabel>Sender Settings</SectionLabel>
          <Field label="Reply-To Email (optional)" hint="Replies from leads go to this address instead of the sender. Leave blank to use sender email.">
            <Input
              value={s.reply_to_email || ''}
              onChange={e => set('reply_to_email', e.target.value)}
              placeholder="replies@decisionpinnacle.co"
            />
          </Field>
        </div>
      </div>

      <div className="space-y-4">
        <SectionLabel>Domain Exclusions</SectionLabel>
        <Field label="Excluded Domains" hint="Never send to emails from these domains. Add personal email domains to only target business emails.">
          <EditableList
            items={s.excluded_domains || []}
            onChange={v => set('excluded_domains', v)}
            placeholder="e.g. gmail.com, yahoo.com, hotmail.com..."
          />
        </Field>
      </div>

      <div className="p-4 bg-primary/5 border border-primary/20 rounded-xl">
        <p className="text-xs text-primary font-medium mb-1">Brevo Free Plan Limits</p>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Free plan: 300 emails/day, 9,000/month. Upgrade to Starter ($25/mo) for 20k/month.
          Remaining leads are marked as NO_EMAIL (with a note in the Error column) if the daily limit is hit.
        </p>
      </div>
    </div>
  )
}

// ── Automation tab ────────────────────────────────────────────────────────────

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
const DAY_SHORT = { monday: 'Mon', tuesday: 'Tue', wednesday: 'Wed', thursday: 'Thu', friday: 'Fri', saturday: 'Sat', sunday: 'Sun' }
const TIMEZONES = ['Asia/Kolkata', 'UTC', 'America/New_York', 'America/Los_Angeles', 'Europe/London', 'Asia/Dubai']

const DEFAULT_FOLDER_VALUE = '__default__'

// Each scheduled time can optionally pin a specific saved search-query
// folder — if none is chosen, that time slot runs whatever folder is
// currently active/default (today's behavior, unchanged).
const DEFAULT_COOKIE_VALUE = '__default__'
const COOKIE_MODE_OPTIONS = [
  { value: DEFAULT_COOKIE_VALUE, label: 'Default (current toggle)' },
  { value: 'cookie', label: 'Cookie mode' },
  { value: 'no_cookie', label: 'No-cookie mode' },
]

function TimeList({ times, timeQuerySets, querySetNames, timeCookieModes, onChange }) {
  const [newTime, setNewTime] = useState('09:00')
  const [newFolder, setNewFolder] = useState(DEFAULT_FOLDER_VALUE)
  const [newCookieMode, setNewCookieMode] = useState(DEFAULT_COOKIE_VALUE)

  const add = () => {
    if (!newTime || times.includes(newTime)) return
    const nextTimes = [...times, newTime].sort()
    const nextFolders = { ...timeQuerySets }
    const nextCookies = { ...timeCookieModes }
    if (newFolder !== DEFAULT_FOLDER_VALUE) nextFolders[newTime] = newFolder
    if (newCookieMode !== DEFAULT_COOKIE_VALUE) nextCookies[newTime] = newCookieMode
    onChange(nextTimes, nextFolders, nextCookies)
    setNewFolder(DEFAULT_FOLDER_VALUE)
    setNewCookieMode(DEFAULT_COOKIE_VALUE)
  }

  const remove = (t) => {
    const nextFolders = { ...timeQuerySets }
    const nextCookies = { ...timeCookieModes }
    delete nextFolders[t]
    delete nextCookies[t]
    onChange(times.filter(x => x !== t), nextFolders, nextCookies)
  }

  const setFolderForTime = (t, folder) => {
    const nextFolders = { ...timeQuerySets }
    if (folder === DEFAULT_FOLDER_VALUE) delete nextFolders[t]
    else nextFolders[t] = folder
    onChange(times, nextFolders, timeCookieModes)
  }

  const setCookieModeForTime = (t, mode) => {
    const nextCookies = { ...timeCookieModes }
    if (mode === DEFAULT_COOKIE_VALUE) delete nextCookies[t]
    else nextCookies[t] = mode
    onChange(times, timeQuerySets, nextCookies)
  }

  const FolderSelect = ({ value, onValueChange, className }) => (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger className={cn('h-8 text-xs', className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={DEFAULT_FOLDER_VALUE}>Default (active saved list)</SelectItem>
        {querySetNames.map(name => <SelectItem key={name} value={name}>{name}</SelectItem>)}
      </SelectContent>
    </Select>
  )

  const CookieSelect = ({ value, onValueChange, className }) => (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger className={cn('h-8 text-xs', className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {COOKIE_MODE_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  )

  return (
    <div className="space-y-2">
      <div className="space-y-1.5">
        {times.map(t => (
          <div key={t} className="flex items-center gap-2 bg-background border border-border rounded-lg px-3 py-1.5 group">
            <span className="text-sm font-mono text-foreground w-14 flex-shrink-0">{t}</span>
            <FolderSelect
              value={timeQuerySets[t] || DEFAULT_FOLDER_VALUE}
              onValueChange={(v) => setFolderForTime(t, v)}
              className="flex-1"
            />
            <CookieSelect
              value={timeCookieModes[t] || DEFAULT_COOKIE_VALUE}
              onValueChange={(v) => setCookieModeForTime(t, v)}
              className="flex-1"
            />
            <button
              onClick={() => remove(t)}
              className="w-5 h-5 rounded flex items-center justify-center text-muted-foreground hover:text-destructive transition-colors opacity-0 group-hover:opacity-100 flex-shrink-0"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
        {times.length === 0 && <p className="text-xs text-muted-foreground italic">No times set</p>}
      </div>
      <div className="flex gap-2">
        <Input
          type="time"
          value={newTime}
          onChange={e => setNewTime(e.target.value)}
          className="w-auto flex-shrink-0"
        />
        <FolderSelect value={newFolder} onValueChange={setNewFolder} className="w-44 flex-shrink-0" />
        <CookieSelect value={newCookieMode} onValueChange={setNewCookieMode} className="w-44 flex-shrink-0" />
        <Button variant="outline" onClick={add} disabled={!newTime || times.includes(newTime)}>Add Time</Button>
      </div>
    </div>
  )
}

function AutomationTab({ cfg, onChange }) {
  const a = cfg.automation || {}
  const set = (key, val) => onChange({ ...cfg, automation: { ...a, [key]: val } })
  const setTimeSchedule = (times, timeQuerySets, timeCookieModes) =>
    onChange({ ...cfg, automation: { ...a, times, time_query_sets: timeQuerySets, time_cookie_modes: timeCookieModes } })
  const querySetNames = Object.keys(cfg.scraping?.query_sets || {})
  const [nextRuns, setNextRuns] = useState([])

  useEffect(() => {
    fetch('/api/automation/next-runs')
      .then(r => r.json())
      .then(d => setNextRuns(d.next_runs || []))
      .catch(() => {})
  }, [a.enabled])

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <SectionLabel>Pipeline Mode</SectionLabel>
        <div className="p-4 bg-background border border-border rounded-xl">
          <div className="flex gap-3">
            <button
              onClick={() => set('enabled', false)}
              className={cn(
                'flex-1 flex flex-col items-center gap-2 px-4 py-4 rounded-xl border-2 transition-all',
                !a.enabled ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:border-border/80 hover:text-foreground'
              )}
            >
              <MousePointerClick className="w-6 h-6" />
              <span className="text-sm font-semibold">Manual</span>
              <span className="text-xs text-center opacity-70">Run only when you click the Run button</span>
            </button>
            <button
              onClick={() => set('enabled', true)}
              className={cn(
                'flex-1 flex flex-col items-center gap-2 px-4 py-4 rounded-xl border-2 transition-all',
                a.enabled ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:border-border/80 hover:text-foreground'
              )}
            >
              <Zap className="w-6 h-6" />
              <span className="text-sm font-semibold">Automated</span>
              <span className="text-xs text-center opacity-70">Runs on a schedule automatically</span>
            </button>
          </div>
        </div>
      </div>

      {a.enabled && (
        <>
          <div className="space-y-4">
            <SectionLabel>Run Days</SectionLabel>
            <ToggleGroup
              type="multiple"
              value={a.days || []}
              onValueChange={(v) => set('days', v)}
              className="flex-wrap justify-start"
            >
              {DAYS.map(day => (
                <ToggleGroupItem key={day} value={day} variant="outline" className="data-[state=on]:bg-primary data-[state=on]:text-primary-foreground data-[state=on]:border-primary">
                  {DAY_SHORT[day]}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            {(a.days || []).length === 0 && (
              <p className="text-xs text-amber-400 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Select at least one day for scheduled runs</p>
            )}
          </div>

          <div className="space-y-4">
            <SectionLabel>Run Times</SectionLabel>
            <Field
              label="Schedule Times"
              hint="The pipeline runs at each of these times on the selected days, in the selected timezone. Optionally pin a specific saved search-query folder and/or cookie vs no-cookie scraping mode to a time — leave either on Default to use whatever's currently active/toggled."
            >
              <TimeList
                times={a.times || []}
                timeQuerySets={a.time_query_sets || {}}
                querySetNames={querySetNames}
                timeCookieModes={a.time_cookie_modes || {}}
                onChange={setTimeSchedule}
              />
            </Field>
          </div>

          <div className="space-y-4">
            <SectionLabel>Timezone</SectionLabel>
            <Field label="Timezone" hint="All scheduled times are interpreted in this timezone">
              <SelectInput
                value={a.timezone || 'Asia/Kolkata'}
                onChange={v => set('timezone', v)}
                options={TIMEZONES.map(tz => ({ value: tz, label: tz }))}
              />
            </Field>
          </div>

          <div className="space-y-3">
            <SectionLabel>Next Scheduled Runs</SectionLabel>
            <div className="p-4 bg-background border border-border rounded-xl">
              {nextRuns.length === 0 ? (
                <p className="text-xs text-muted-foreground italic">Save your settings to see scheduled times</p>
              ) : (
                <div className="space-y-2">
                  {nextRuns.slice(0, 5).map((t, i) => {
                    const d = new Date(t)
                    return (
                      <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
                        <ClockIcon className="w-3 h-3 text-emerald-400 flex-shrink-0" />
                        {d.toLocaleString('en-IN', { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true })}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {!a.enabled && (
        <div className="p-4 bg-background border border-border rounded-xl">
          <p className="text-xs text-muted-foreground leading-relaxed">
            In <strong className="text-foreground">Manual mode</strong>, the pipeline only runs when you click the{' '}
            <strong className="text-foreground">Run Pipeline</strong> button on the Dashboard.
            No automatic runs will occur.
          </p>
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function AdminPanel() {
  const [activeTab, setActiveTab] = useState('Scraping')
  const [config, setConfig] = useState(null)
  const [saved, setSaved] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch('/api/admin/config')
      .then(r => r.json())
      .then(data => {
        setConfig(data)
        setSaved(JSON.stringify(data))
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const isDirty = config && JSON.stringify(config) !== saved

  const save = async () => {
    setSaving(true)
    try {
      const res = await fetch('/api/admin/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      if (!res.ok) throw new Error('Save failed')
      setSaved(JSON.stringify(config))
      toast.success('Settings saved — takes effect on next run')
    } catch (e) {
      toast.error('Save failed — check the backend is reachable')
    }
    setSaving(false)
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-primary animate-spin" />
      </div>
    )
  }

  if (!config) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
        Failed to load config. Is the backend running?
      </div>
    )
  }

  const TAB_PANELS = {
    'Scraping': <ScrapingTab cfg={config} onChange={setConfig} />,
    'AI Filtering': <FilteringTab cfg={config} onChange={setConfig} />,
    'Enrichment': <EnrichmentTab cfg={config} onChange={setConfig} />,
    'Email Sending': <SendingTab cfg={config} onChange={setConfig} />,
    'Automation': <AutomationTab cfg={config} onChange={setConfig} />,
  }

  return (
    <div className="h-full flex flex-col overflow-hidden p-6 gap-4">
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-lg font-bold text-foreground">Admin Panel</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Pipeline settings — changes take effect on the next Run</p>
        </div>
        <Button onClick={save} disabled={!isDirty || saving} className="gap-2">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? 'Saving...' : isDirty ? 'Save Changes' : 'No Changes'}
        </Button>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col overflow-hidden">
        <TabsList className="flex-shrink-0 w-full justify-start">
          {TABS.map(tab => (
            <TabsTrigger key={tab} value={tab} className="gap-1.5">
              {tab}
              {tab === 'Email Sending' && config?.sending?.dry_run_mode && (
                <Badge variant="outline" className="ml-1 text-[10px] px-1 py-0 h-4 border-amber-500/40 text-amber-400">DRY RUN</Badge>
              )}
              {tab === 'Automation' && config?.automation?.enabled && (
                <Badge variant="outline" className="ml-1 text-[10px] px-1 py-0 h-4 border-emerald-500/40 text-emerald-400">ON</Badge>
              )}
            </TabsTrigger>
          ))}
        </TabsList>

        <Separator className="flex-shrink-0" />

        <div className="flex-1 overflow-y-auto pt-4">
          <div className="max-w-3xl">
            {TAB_PANELS[activeTab]}
          </div>
        </div>
      </Tabs>
    </div>
  )
}
