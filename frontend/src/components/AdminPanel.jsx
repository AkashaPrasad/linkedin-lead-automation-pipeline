import { useState, useEffect } from 'react'

const TABS = ['Scraping', 'AI Filtering', 'Enrichment', 'Email Sending']

// ── Reusable UI pieces ────────────────────────────────────────────────────────

function SectionLabel({ children }) {
  return <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-widest mb-3">{children}</h4>
}

function Field({ label, hint, children }) {
  return (
    <div className="space-y-1.5">
      <div>
        <label className="text-sm font-medium text-text-primary">{label}</label>
        {hint && <p className="text-xs text-text-muted mt-0.5">{hint}</p>}
      </div>
      {children}
    </div>
  )
}

function NumberInput({ value, onChange, min = 0, max = 99999, step = 1 }) {
  return (
    <input
      type="number"
      value={value}
      onChange={e => onChange(Number(e.target.value))}
      min={min}
      max={max}
      step={step}
      className="w-full bg-bg-primary border border-border-color rounded-lg px-4 py-2.5 text-sm text-text-primary focus:outline-none focus:border-purple-primary/50 transition-colors"
    />
  )
}

function TextInput({ value, onChange, placeholder = '' }) {
  return (
    <input
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full bg-bg-primary border border-border-color rounded-lg px-4 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-primary/50 transition-colors"
    />
  )
}

function SelectInput({ value, onChange, options }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full bg-bg-primary border border-border-color rounded-lg px-4 py-2.5 text-sm text-text-primary focus:outline-none focus:border-purple-primary/50 transition-colors"
    >
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

function Toggle({ value, onChange, label, hint }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-medium text-text-primary">{label}</p>
        {hint && <p className="text-xs text-text-muted mt-0.5">{hint}</p>}
      </div>
      <button
        onClick={() => onChange(!value)}
        className={`relative flex-shrink-0 w-11 h-6 rounded-full transition-colors ${value ? 'bg-purple-primary' : 'bg-bg-tertiary border border-border-color'}`}
      >
        <div className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform shadow ${value ? 'translate-x-5' : ''}`} />
      </button>
    </div>
  )
}

// ── Editable list (like Apify keyword UI) ─────────────────────────────────────
function EditableList({ items, onChange, placeholder = 'Add item...', addLabel = '+ Add' }) {
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
      {/* Existing items */}
      <div className="space-y-1.5">
        {items.map((item, i) => (
          <div
            key={i}
            className="flex items-center gap-2 bg-bg-primary border border-border-color rounded-lg px-3 py-2 group"
          >
            <span className="w-6 h-6 rounded-md bg-purple-primary/10 text-purple-light text-xs font-bold flex items-center justify-center flex-shrink-0">
              {i + 1}
            </span>
            <span className="flex-1 text-sm text-text-primary font-mono">{item}</span>
            <button
              onClick={() => remove(i)}
              className="w-6 h-6 rounded flex items-center justify-center text-text-muted hover:text-red-accent hover:bg-red-accent/10 transition-colors opacity-0 group-hover:opacity-100"
            >
              ✕
            </button>
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-xs text-text-muted italic px-1">No items — add one below</p>
        )}
      </div>

      {/* Add new */}
      <div className="flex gap-2">
        <input
          type="text"
          value={newItem}
          onChange={e => setNewItem(e.target.value)}
          onKeyDown={handleKey}
          placeholder={placeholder}
          className="flex-1 bg-bg-primary border border-border-color rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-primary/50 transition-colors"
        />
        <button
          onClick={add}
          disabled={!newItem.trim()}
          className="px-4 py-2 rounded-lg bg-purple-primary/10 border border-purple-primary/30 text-purple-light text-sm font-medium hover:bg-purple-primary/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {addLabel}
        </button>
      </div>
    </div>
  )
}

// ── Tab panels ────────────────────────────────────────────────────────────────

function ScrapingTab({ cfg, onChange }) {
  const s = cfg.scraping || {}
  const set = (key, val) => onChange({ ...cfg, scraping: { ...s, [key]: val } })
  const flt = cfg.filtering || {}
  const setF = (key, val) => onChange({ ...cfg, filtering: { ...flt, [key]: val } })

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <SectionLabel>Search Keywords</SectionLabel>
        <Field
          label="Search Queries"
          hint="LinkedIn posts matching any of these keywords will be scraped. Use specific phrases for better lead quality."
        >
          <EditableList
            items={s.search_queries || []}
            onChange={v => set('search_queries', v)}
            placeholder="Add a search keyword or phrase..."
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-4">
          <SectionLabel>Post Limits</SectionLabel>
          <Field label="Max Posts Per Keyword" hint="How many posts to scrape for each search query (max 200)">
            <NumberInput value={s.max_posts_per_query || 50} onChange={v => set('max_posts_per_query', v)} min={10} max={200} step={10} />
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
              addLabel="+ Add"
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
              addLabel="+ Add"
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
        <div className="p-4 bg-bg-primary border border-border-color rounded-xl space-y-4">
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
      {/* Apollo plan warning */}
      {apolloPlan && !apolloPlan.accessible && (
        <div className="flex items-start gap-3 p-4 bg-amber-accent/10 border border-amber-accent/40 rounded-xl">
          <span className="text-xl flex-shrink-0">⚠</span>
          <div className="flex-1">
            <p className="text-sm font-bold text-amber-accent">Apollo Email Enrichment Not Available</p>
            <p className="text-xs text-amber-accent/80 mt-1 leading-relaxed">
              {apolloPlan.reason}. Your current plan does not include the people lookup API.
              This means leads without an email in their post will be marked <strong>NO_EMAIL</strong> and won't receive your outreach.
            </p>
            <p className="text-xs text-amber-accent/80 mt-2">
              To fix: upgrade to <strong>Apollo Starter ($49/month)</strong> — includes 300 email lookups/month.{' '}
              <a href="https://app.apollo.io/settings/plans" target="_blank" rel="noreferrer"
                 className="underline hover:no-underline">Upgrade Apollo plan ↗</a>
            </p>
            <p className="text-xs text-text-muted mt-2">
              Alternative for now: use the <strong>Only posts with email</strong> toggle in AI Filtering tab to focus only on posts that already have an email address visible.
            </p>
          </div>
        </div>
      )}
      {apolloPlan?.accessible && (
        <div className="flex items-center gap-2 p-3 bg-green-accent/10 border border-green-accent/30 rounded-xl">
          <span className="text-green-accent">✓</span>
          <p className="text-xs text-green-accent font-medium">Apollo email enrichment is active and working on your plan.</p>
        </div>
      )}

      <div className="space-y-4">
        <SectionLabel>Apollo.io Enrichment (Stage 6)</SectionLabel>
        <div className="p-4 bg-bg-primary border border-border-color rounded-xl space-y-4">
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
        <Field
          label="Max Enrichment Lookups Per Run"
          hint="Apollo free plan gives limited lookups/month. Cap this to avoid burning through your quota in one run."
        >
          <NumberInput value={e.max_enrichment_per_run || 100} onChange={v => set('max_enrichment_per_run', v)} min={10} max={500} step={10} />
        </Field>
      </div>

      <div className="p-4 bg-amber-accent/5 border border-amber-accent/20 rounded-xl">
        <p className="text-xs text-amber-accent font-medium mb-1">Apollo Quota Tip</p>
        <p className="text-xs text-text-secondary leading-relaxed">
          Apollo free plan: 50 email credits/month. Paid plans start at $49/month for 300 credits.
          Email credits are only consumed when Apollo finds a valid email — not for "not found" responses.
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
        <div className="p-4 bg-bg-primary border border-border-color rounded-xl space-y-4">
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
            <TextInput
              value={s.reply_to_email || ''}
              onChange={v => set('reply_to_email', v)}
              placeholder="replies@decisionpinnacle.co"
            />
          </Field>
        </div>
      </div>

      <div className="space-y-4">
        <SectionLabel>Domain Exclusions</SectionLabel>
        <Field
          label="Excluded Domains"
          hint="Never send to emails from these domains. Add personal email domains to only target business emails."
        >
          <EditableList
            items={s.excluded_domains || []}
            onChange={v => set('excluded_domains', v)}
            placeholder="e.g. gmail.com, yahoo.com, hotmail.com..."
          />
        </Field>
      </div>

      <div className="p-4 bg-purple-primary/5 border border-purple-primary/20 rounded-xl">
        <p className="text-xs text-purple-light font-medium mb-1">Brevo Free Plan Limits</p>
        <p className="text-xs text-text-secondary leading-relaxed">
          Free plan: 300 emails/day, 9,000/month. Upgrade to Starter ($25/mo) for 20k/month.
          The pipeline will mark remaining emails as CAPPED if the daily limit is hit.
        </p>
      </div>
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
  const [saveStatus, setSaveStatus] = useState(null)

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
    setSaveStatus(null)
    try {
      const res = await fetch('/api/admin/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      if (!res.ok) throw new Error('Save failed')
      setSaved(JSON.stringify(config))
      setSaveStatus('saved')
      setTimeout(() => setSaveStatus(null), 3000)
    } catch (e) {
      setSaveStatus('error')
    }
    setSaving(false)
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-purple-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!config) {
    return (
      <div className="h-full flex items-center justify-center text-text-muted text-sm">
        Failed to load config. Is the backend running?
      </div>
    )
  }

  const TAB_PANELS = {
    'Scraping': <ScrapingTab cfg={config} onChange={setConfig} />,
    'AI Filtering': <FilteringTab cfg={config} onChange={setConfig} />,
    'Enrichment': <EnrichmentTab cfg={config} onChange={setConfig} />,
    'Email Sending': <SendingTab cfg={config} onChange={setConfig} />,
  }

  return (
    <div className="h-full flex flex-col overflow-hidden p-6 gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-lg font-bold text-text-primary">Admin Panel</h2>
          <p className="text-xs text-text-muted mt-0.5">
            Pipeline settings — changes take effect on the next Run
          </p>
        </div>
        <div className="flex items-center gap-3">
          {saveStatus === 'saved' && (
            <span className="text-xs text-green-accent flex items-center gap-1">
              <span>✓</span> Saved — takes effect on next run
            </span>
          )}
          {saveStatus === 'error' && (
            <span className="text-xs text-red-accent">Save failed</span>
          )}
          <button
            onClick={save}
            disabled={!isDirty || saving}
            className={`flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium transition-all ${
              isDirty && !saving
                ? 'bg-purple-primary text-white hover:bg-purple-primary/90'
                : 'bg-bg-tertiary text-text-muted cursor-not-allowed'
            }`}
          >
            {saving ? (
              <>
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Saving...
              </>
            ) : isDirty ? 'Save Changes' : 'No Changes'}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 flex-shrink-0 bg-bg-secondary border border-border-color rounded-xl p-1">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === tab
                ? 'bg-purple-primary text-white'
                : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
            }`}
          >
            {tab}
            {tab === 'Email Sending' && config?.sending?.dry_run_mode && (
              <span className="ml-1.5 text-amber-accent text-xs">DRY RUN</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl">
          {TAB_PANELS[activeTab]}
        </div>
      </div>
    </div>
  )
}
