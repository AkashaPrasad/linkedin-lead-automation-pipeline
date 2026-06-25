import { useState, useEffect, useRef, useCallback } from 'react'

const SERVICE_CATEGORIES = ['Growth', 'Production', 'Influencer Marketing', 'Branding']
// "Creative" (main) is the parent fallback — used when the AI knows the lead is a
// creative-type ask but the brand's industry doesn't fit any of the 5 sub-categories.
const CREATIVE_MAIN = 'Creative'
const CREATIVE_SUBCATEGORIES = ['Creative - FMCG', 'Creative - Real Estate', 'Creative - Apparel', 'Creative - Kids', 'Creative - Beauty']
const CATEGORIES = [...SERVICE_CATEGORIES, CREATIVE_MAIN, ...CREATIVE_SUBCATEGORIES, 'Generic']

const CATEGORY_COLORS = {
  'Growth': 'text-green-accent border-green-accent/30 bg-green-accent/5',
  'Production': 'text-blue-400 border-blue-400/30 bg-blue-400/5',
  'Influencer Marketing': 'text-orange-400 border-orange-400/30 bg-orange-400/5',
  'Branding': 'text-amber-accent border-amber-accent/30 bg-amber-accent/5',
  'Creative': 'text-purple-light border-purple-primary/40 bg-purple-primary/10',
  'Creative - FMCG': 'text-purple-light border-purple-primary/30 bg-purple-primary/5',
  'Creative - Real Estate': 'text-purple-light border-purple-primary/30 bg-purple-primary/5',
  'Creative - Apparel': 'text-purple-light border-purple-primary/30 bg-purple-primary/5',
  'Creative - Kids': 'text-purple-light border-purple-primary/30 bg-purple-primary/5',
  'Creative - Beauty': 'text-purple-light border-purple-primary/30 bg-purple-primary/5',
  'Generic': 'text-text-secondary border-border-color bg-bg-tertiary',
}

const VARIABLES = [
  {
    key: '{{first_name}}',
    label: 'first_name',
    description: 'First name of the lead — extracted from their LinkedIn name (e.g. "Rahul")',
    example: 'Rahul',
  },
  {
    key: '{{company}}',
    label: 'company',
    description: 'Company name — extracted from the part after "at" or "@" in their headline (e.g. "BeautyBrand"). Falls back to full headline if no company found.',
    example: 'BeautyBrand',
  },
  {
    key: '{{post_snippet}}',
    label: 'post_snippet',
    description: 'First 100 characters of their LinkedIn post. This makes the email feel personal — they see you actually read their post.',
    example: 'Looking for a marketing agency to scale our D2C brand on Instagram and Amazon',
  },
]

// ── Highlighted textarea (overlay technique) ──────────────────────────────────
function HighlightTextarea({ value, onChange }) {
  const textareaRef = useRef(null)
  const backdropRef = useRef(null)

  const getHighlightedHtml = (text) => {
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    return escaped
      .replace(
        /(\{\{[^}]+\}\})/g,
        '<mark style="background:rgba(168,85,247,0.18);color:#C084FC;border-radius:2px;padding:0 1px;">$1</mark>'
      )
      .replace(/\n/g, '<br>')
  }

  const syncScroll = useCallback(() => {
    if (backdropRef.current && textareaRef.current) {
      backdropRef.current.scrollTop = textareaRef.current.scrollTop
    }
  }, [])

  const sharedStyle = {
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    fontSize: '13px',
    lineHeight: '1.75',
    padding: '16px',
    margin: 0,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    overflowWrap: 'break-word',
    width: '100%',
    height: '100%',
    boxSizing: 'border-box',
  }

  return (
    <div style={{ position: 'relative', flex: 1, minHeight: 0, overflow: 'hidden' }}>
      {/* Highlight backdrop */}
      <div
        ref={backdropRef}
        aria-hidden="true"
        style={{
          ...sharedStyle,
          position: 'absolute',
          top: 0, left: 0, right: 0, bottom: 0,
          pointerEvents: 'none',
          color: '#94A3B8',
          background: 'transparent',
          overflow: 'hidden',
        }}
        dangerouslySetInnerHTML={{ __html: getHighlightedHtml(value) + '​' }}
      />
      {/* Actual textarea — transparent text, visible caret */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={e => onChange(e.target.value)}
        onScroll={syncScroll}
        spellCheck={false}
        style={{
          ...sharedStyle,
          position: 'relative',
          background: 'transparent',
          color: 'transparent',
          caretColor: '#F1F5F9',
          resize: 'none',
          border: 'none',
          outline: 'none',
          overflowY: 'auto',
        }}
      />
      {/* Custom placeholder */}
      {!value && (
        <div
          aria-hidden="true"
          style={{
            position: 'absolute', top: 0, left: 0, pointerEvents: 'none',
            padding: '16px', color: '#475569',
            fontFamily: "'JetBrains Mono', monospace", fontSize: '13px', lineHeight: '1.75',
          }}
        >
          Write your email body here...{'\n'}Use {'{{first_name}}'}, {'{{company}}'}, {'{{post_snippet}}'} for personalisation.{'\n'}Variables will highlight purple as you type them.
        </div>
      )}
    </div>
  )
}

// ── Variable status chips ─────────────────────────────────────────────────────
function VarStatus({ body }) {
  return (
    <div className="flex items-start gap-4 flex-shrink-0">
      <span className="text-xs text-text-muted font-medium pt-0.5 flex-shrink-0">Variables:</span>
      <div className="flex flex-wrap gap-2">
        {VARIABLES.map(v => {
          const found = body.includes(v.key)
          return (
            <div key={v.key} className="group relative">
              <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono border transition-colors ${
                found
                  ? 'bg-purple-primary/10 text-purple-light border-purple-primary/30'
                  : 'bg-bg-tertiary text-text-muted border-border-color'
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${found ? 'bg-purple-light' : 'bg-text-muted'}`} />
                {v.key}
                {found ? ' ✓' : ''}
              </span>
              {/* Tooltip */}
              <div className="absolute bottom-full left-0 mb-2 w-64 p-3 bg-bg-primary border border-border-color rounded-lg text-xs text-text-secondary hidden group-hover:block z-20 shadow-xl">
                <p className="font-semibold text-text-primary mb-1">{v.key}</p>
                <p className="leading-relaxed mb-2">{v.description}</p>
                <p className="text-text-muted">Example: <span className="text-purple-light">{v.example}</span></p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Variable reference panel ──────────────────────────────────────────────────
function VariableReference() {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex-shrink-0">
      <button
        onClick={() => setOpen(o => !o)}
        className="text-xs text-purple-light hover:text-purple-primary flex items-center gap-1 transition-colors"
      >
        <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4M12 8h.01" />
        </svg>
        What are these variables?
      </button>
      {open && (
        <div className="mt-3 p-4 bg-bg-primary border border-border-color rounded-xl space-y-3">
          <p className="text-xs font-semibold text-text-primary">Variables are auto-filled for each lead at send time:</p>
          {VARIABLES.map(v => (
            <div key={v.key} className="flex gap-3">
              <code className="text-xs text-purple-light font-mono flex-shrink-0 pt-0.5 w-36">{v.key}</code>
              <div>
                <p className="text-xs text-text-secondary leading-relaxed">{v.description}</p>
                <p className="text-xs text-text-muted mt-0.5">e.g. <span className="text-text-secondary">"{v.example}"</span></p>
              </div>
            </div>
          ))}
          <p className="text-xs text-amber-accent/80 border-t border-border-color pt-3">
            ⚠ If a variable can't be extracted (e.g. no "at" in headline), a sensible fallback is used.
          </p>
        </div>
      )}
    </div>
  )
}

// ── Test email modal ──────────────────────────────────────────────────────────
function TestEmailModal({ defaultCategory, templates, onClose }) {
  const [email, setEmail] = useState('')
  const [category, setCategory] = useState(defaultCategory)
  const [vars, setVars] = useState({
    first_name: 'Rahul',
    company: 'BeautyBrand',
    post_snippet: 'Looking for a marketing agency to scale our D2C brand on Instagram and Amazon',
  })
  const [status, setStatus] = useState(null)
  const [errMsg, setErrMsg] = useState('')
  const [showPreview, setShowPreview] = useState(false)

  const tmpl = (templates[category] || templates['Generic'] || { subject: '', body: '' })
  const rendered = {
    subject: tmpl.subject
      .replace(/{{first_name}}/g, vars.first_name)
      .replace(/{{company}}/g, vars.company)
      .replace(/{{post_snippet}}/g, vars.post_snippet),
    body: tmpl.body
      .replace(/{{first_name}}/g, vars.first_name)
      .replace(/{{company}}/g, vars.company)
      .replace(/{{post_snippet}}/g, vars.post_snippet),
  }

  const send = async () => {
    if (!email || !email.includes('@')) {
      setErrMsg('Please enter a valid email address')
      return
    }
    setStatus('sending')
    setErrMsg('')
    try {
      const res = await fetch('/api/test-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, category, ...vars }),
      })
      let data
      try { data = await res.json() } catch { data = {} }
      if (!res.ok) {
        throw new Error(data.detail || `Server error ${res.status}`)
      }
      setStatus('success')
    } catch (e) {
      setStatus('error')
      setErrMsg(e.message)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-bg-secondary border border-border-color rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-color flex-shrink-0">
          <div>
            <h3 className="text-base font-bold text-text-primary">Send Test Email</h3>
            <p className="text-xs text-text-muted mt-0.5">See exactly what the lead will receive</p>
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary transition-colors">
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Recipient */}
          <div>
            <label className="text-xs text-text-muted font-medium uppercase tracking-wide block mb-1.5">
              Send to (your email to test)
            </label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full bg-bg-tertiary border border-border-color rounded-lg px-4 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-primary/50 transition-colors"
            />
          </div>

          {/* Category */}
          <div>
            <label className="text-xs text-text-muted font-medium uppercase tracking-wide block mb-1.5">
              Template Category
            </label>
            <select
              value={category}
              onChange={e => setCategory(e.target.value)}
              className="w-full bg-bg-tertiary border border-border-color rounded-lg px-4 py-2.5 text-sm text-text-primary focus:outline-none focus:border-purple-primary/50 transition-colors"
            >
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          {/* Test variable values */}
          <div>
            <label className="text-xs text-text-muted font-medium uppercase tracking-wide block mb-2">
              Test Variable Values
            </label>
            <div className="space-y-3">
              {VARIABLES.map(v => (
                <div key={v.key}>
                  <div className="flex items-center gap-2 mb-1">
                    <code className="text-xs text-purple-light font-mono">{v.key}</code>
                    <span className="text-xs text-text-muted">— {v.description.split('(')[0].trim()}</span>
                  </div>
                  <input
                    type="text"
                    value={vars[v.label] || ''}
                    onChange={e => setVars(p => ({ ...p, [v.label]: e.target.value }))}
                    className="w-full bg-bg-tertiary border border-border-color rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-purple-primary/50 transition-colors"
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Preview toggle */}
          <div>
            <button
              onClick={() => setShowPreview(p => !p)}
              className="text-xs text-purple-light hover:underline"
            >
              {showPreview ? '▲ Hide email preview' : '▼ Show email preview'}
            </button>
            {showPreview && (
              <div className="mt-3 bg-white rounded-xl p-5 overflow-auto max-h-60">
                <p className="text-xs text-gray-400 mb-1">Subject</p>
                <p className="text-sm font-semibold text-gray-900 mb-4">{rendered.subject}</p>
                <hr className="border-gray-200 mb-4" />
                <pre className="text-sm text-gray-800 whitespace-pre-wrap font-sans leading-relaxed">
                  {rendered.body}
                </pre>
              </div>
            )}
          </div>

          {/* Status */}
          {status === 'success' && (
            <div className="flex items-center gap-2 p-3 bg-green-accent/10 border border-green-accent/30 rounded-lg">
              <span className="text-green-accent">✓</span>
              <p className="text-sm text-green-accent font-medium">Email sent successfully! Check your inbox.</p>
            </div>
          )}
          {status === 'error' && (
            <div className="flex items-start gap-2 p-3 bg-red-accent/10 border border-red-accent/30 rounded-lg">
              <span className="text-red-accent mt-0.5">⚠</span>
              <p className="text-sm text-red-accent">{errMsg}</p>
            </div>
          )}
          {errMsg && status !== 'error' && (
            <p className="text-xs text-red-accent">{errMsg}</p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border-color flex-shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-border-color text-text-secondary text-sm hover:text-text-primary transition-colors"
          >
            Close
          </button>
          <button
            onClick={send}
            disabled={status === 'sending'}
            className={`flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium transition-all ${
              status === 'sending'
                ? 'bg-bg-tertiary text-text-muted cursor-not-allowed'
                : 'bg-purple-primary text-white hover:bg-purple-primary/90'
            }`}
          >
            {status === 'sending' ? (
              <>
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Sending...
              </>
            ) : 'Send Test Email'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function TemplateEditor() {
  const [activeCategory, setActiveCategory] = useState('Generic')
  const [templates, setTemplates] = useState({})
  const [saved, setSaved] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [showTestModal, setShowTestModal] = useState(false)
  const [lastEdited, setLastEdited] = useState({})

  useEffect(() => {
    fetch('/api/templates')
      .then(r => r.json())
      .then(data => {
        setTemplates(data)
        setSaved(JSON.parse(JSON.stringify(data)))
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const current = templates[activeCategory] || { subject: '', body: '' }
  const isDirty = JSON.stringify(current) !== JSON.stringify(saved[activeCategory] || {})

  const update = (field, value) => {
    setTemplates(prev => ({
      ...prev,
      [activeCategory]: { ...prev[activeCategory], [field]: value },
    }))
  }

  const save = async () => {
    setSaving(true)
    try {
      await fetch('/api/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(templates),
      })
      setSaved(JSON.parse(JSON.stringify(templates)))
      setLastEdited(prev => ({ ...prev, [activeCategory]: new Date().toLocaleTimeString() }))
    } catch (e) {
      alert('Save failed: ' + e.message)
    }
    setSaving(false)
  }

  const renderPreview = (template) => ({
    subject: (template.subject || '')
      .replace(/{{first_name}}/g, 'Rahul')
      .replace(/{{company}}/g, 'BeautyBrand')
      .replace(/{{post_snippet}}/g, 'Looking for a marketing agency to scale our D2C brand...'),
    body: (template.body || '')
      .replace(/{{first_name}}/g, 'Rahul')
      .replace(/{{company}}/g, 'BeautyBrand')
      .replace(/{{post_snippet}}/g, 'Looking for a marketing agency to scale our D2C brand...'),
  })

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-purple-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col overflow-hidden p-6 gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-lg font-bold text-text-primary">Email Templates</h2>
          <p className="text-xs text-text-muted mt-0.5">Edit the personalised email for each lead category — variables highlight as you type</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowTestModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-amber-accent/30 text-amber-accent text-sm hover:bg-amber-accent/5 transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
              <polyline points="22,6 12,13 2,6" />
            </svg>
            Test Email
          </button>
          <button
            onClick={() => setShowPreview(p => !p)}
            className="px-4 py-2 rounded-lg border border-border-color text-text-secondary text-sm hover:text-text-primary hover:border-purple-primary/30 transition-colors"
          >
            {showPreview ? 'Hide Preview' : 'Preview'}
          </button>
          <button
            onClick={save}
            disabled={!isDirty || saving}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              isDirty && !saving
                ? 'bg-purple-primary text-white hover:bg-purple-primary/90'
                : 'bg-bg-tertiary text-text-muted cursor-not-allowed'
            }`}
          >
            {saving ? 'Saving...' : isDirty ? 'Save Changes' : 'Saved'}
          </button>
        </div>
      </div>

      {/* Category tabs */}
      <div className="flex flex-col gap-2 flex-shrink-0">
        <div className="flex gap-2 flex-wrap items-center">
          {[...SERVICE_CATEGORIES, 'Generic'].map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition-all ${
                activeCategory === cat
                  ? CATEGORY_COLORS[cat]
                  : 'text-text-muted border-transparent hover:text-text-primary hover:bg-bg-tertiary'
              }`}
            >
              {cat}
              {JSON.stringify(templates[cat]) !== JSON.stringify(saved[cat]) && (
                <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-amber-accent inline-block" />
              )}
            </button>
          ))}
        </div>
        <div className="flex gap-2 flex-wrap items-center">
          <span className="text-xs text-text-muted font-semibold uppercase tracking-wide pr-1">Creative:</span>
          <button
            onClick={() => setActiveCategory(CREATIVE_MAIN)}
            title="Fallback used when the AI knows it's a creative-type ask but the industry doesn't fit any sub-category below"
            className={`px-4 py-2 rounded-lg text-sm font-semibold border transition-all ${
              activeCategory === CREATIVE_MAIN
                ? CATEGORY_COLORS[CREATIVE_MAIN]
                : 'text-text-muted border-transparent hover:text-text-primary hover:bg-bg-tertiary'
            }`}
          >
            Main
            {JSON.stringify(templates[CREATIVE_MAIN]) !== JSON.stringify(saved[CREATIVE_MAIN]) && (
              <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-amber-accent inline-block" />
            )}
          </button>
          <span className="w-px h-5 bg-border-color" />
          {CREATIVE_SUBCATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition-all ${
                activeCategory === cat
                  ? CATEGORY_COLORS[cat]
                  : 'text-text-muted border-transparent hover:text-text-primary hover:bg-bg-tertiary'
              }`}
            >
              {cat.replace('Creative - ', '')}
              {JSON.stringify(templates[cat]) !== JSON.stringify(saved[cat]) && (
                <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-amber-accent inline-block" />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Editor + preview */}
      <div className={`flex-1 grid gap-4 min-h-0 ${showPreview ? 'grid-cols-2' : 'grid-cols-1'}`}>
        {/* Editor column */}
        <div className="flex flex-col gap-3 min-h-0">
          {/* Subject */}
          <div className="flex-shrink-0">
            <label className="text-xs text-text-muted font-medium uppercase tracking-wide block mb-1.5">
              Subject Line
            </label>
            <div className="relative">
              <input
                type="text"
                value={current.subject || ''}
                onChange={e => update('subject', e.target.value)}
                className="w-full bg-bg-secondary border border-border-color rounded-lg px-4 py-2.5 text-sm text-text-primary focus:outline-none focus:border-purple-primary/50 transition-colors"
                placeholder="Email subject..."
              />
              {/* Highlight variables in subject preview */}
              {current.subject && /\{\{[^}]+\}\}/.test(current.subject) && (
                <div className="absolute inset-0 px-4 py-2.5 pointer-events-none flex items-center">
                  <span className="text-sm">
                    {current.subject.split(/(\{\{[^}]+\}\})/g).map((part, i) =>
                      /^\{\{/.test(part)
                        ? <span key={i} className="text-purple-light">{part}</span>
                        : <span key={i} className="text-transparent">{part}</span>
                    )}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Body */}
          <div className="flex-1 flex flex-col min-h-0 gap-2">
            <div className="flex items-center justify-between">
              <label className="text-xs text-text-muted font-medium uppercase tracking-wide">
                Email Body
              </label>
              {lastEdited[activeCategory] && (
                <span className="text-xs text-text-muted">Saved {lastEdited[activeCategory]}</span>
              )}
            </div>

            {/* Textarea with highlight overlay */}
            <div className="flex-1 min-h-0 bg-bg-secondary border border-border-color rounded-lg overflow-hidden focus-within:border-purple-primary/50 transition-colors flex flex-col">
              <HighlightTextarea
                value={current.body || ''}
                onChange={v => update('body', v)}
              />
            </div>
          </div>

          {/* Variable status + reference */}
          <div className="flex-shrink-0 space-y-2">
            <VarStatus body={current.body || ''} />
            <VariableReference />
          </div>
        </div>

        {/* Preview column */}
        {showPreview && (
          <div className="flex flex-col gap-3 min-h-0">
            <label className="text-xs text-text-muted font-medium uppercase tracking-wide flex-shrink-0">
              Preview (with sample data)
            </label>
            <div className="flex-1 bg-white rounded-xl overflow-auto p-6 min-h-0">
              <div className="mb-4 pb-4 border-b border-gray-200">
                <p className="text-xs text-gray-400 mb-1">Subject</p>
                <p className="text-sm font-semibold text-gray-900">{renderPreview(current).subject}</p>
              </div>
              <pre className="text-sm text-gray-800 whitespace-pre-wrap font-sans leading-relaxed">
                {renderPreview(current).body}
              </pre>
            </div>
          </div>
        )}
      </div>

      {/* Test email modal */}
      {showTestModal && (
        <TestEmailModal
          defaultCategory={activeCategory}
          templates={templates}
          onClose={() => setShowTestModal(false)}
        />
      )}
    </div>
  )
}
