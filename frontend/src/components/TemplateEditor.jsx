import { useState, useEffect, useRef, useCallback } from 'react'
import { toast } from 'sonner'
import {
  HelpCircle, Send, Eye, EyeOff, Save, Loader2, CheckCircle2, AlertTriangle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'

const SERVICE_CATEGORIES = ['Growth', 'Production', 'Influencer Marketing', 'Branding']
// "Creative" (main) is the parent fallback — used when the AI knows the lead is a
// creative-type ask but the brand's industry doesn't fit any of the 5 sub-categories.
const CREATIVE_MAIN = 'Creative'
const CREATIVE_SUBCATEGORIES = ['Creative - FMCG', 'Creative - Real Estate', 'Creative - Apparel', 'Creative - Kids', 'Creative - Beauty']
const CATEGORIES = [...SERVICE_CATEGORIES, CREATIVE_MAIN, ...CREATIVE_SUBCATEGORIES, 'Generic']

const CATEGORY_COLORS = {
  'Growth': 'text-emerald-400 border-emerald-500/30 bg-emerald-500/5',
  'Production': 'text-sky-400 border-sky-500/30 bg-sky-500/5',
  'Influencer Marketing': 'text-orange-400 border-orange-500/30 bg-orange-500/5',
  'Branding': 'text-amber-400 border-amber-500/30 bg-amber-500/5',
  'Creative': 'text-primary border-primary/40 bg-primary/10',
  'Creative - FMCG': 'text-primary border-primary/30 bg-primary/5',
  'Creative - Real Estate': 'text-primary border-primary/30 bg-primary/5',
  'Creative - Apparel': 'text-primary border-primary/30 bg-primary/5',
  'Creative - Kids': 'text-primary border-primary/30 bg-primary/5',
  'Creative - Beauty': 'text-primary border-primary/30 bg-primary/5',
  'Generic': 'text-muted-foreground border-border bg-secondary',
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
// Bespoke DOM-overlay text highlighting — not something a shadcn primitive
// replaces, left as-is functionally. Colors are kept literal since they render
// into a raw HTML string via dangerouslySetInnerHTML, not Tailwind classes.
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
      <span className="text-xs text-muted-foreground font-medium pt-0.5 flex-shrink-0">Variables:</span>
      <div className="flex flex-wrap gap-2">
        {VARIABLES.map(v => {
          const found = body.includes(v.key)
          return (
            <div key={v.key} className="group relative">
              <span className={cn(
                'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono border transition-colors',
                found ? 'bg-primary/10 text-primary border-primary/30' : 'bg-secondary text-muted-foreground border-border'
              )}>
                <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', found ? 'bg-primary' : 'bg-muted-foreground')} />
                {v.key}
                {found && <CheckCircle2 className="w-3 h-3" />}
              </span>
              <div className="absolute bottom-full left-0 mb-2 w-64 p-3 bg-popover border border-border rounded-lg text-xs text-muted-foreground hidden group-hover:block z-20 shadow-xl">
                <p className="font-semibold text-foreground mb-1">{v.key}</p>
                <p className="leading-relaxed mb-2">{v.description}</p>
                <p className="text-muted-foreground">Example: <span className="text-primary">{v.example}</span></p>
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
        className="text-xs text-primary hover:text-primary/80 flex items-center gap-1 transition-colors"
      >
        <HelpCircle className="w-3 h-3" />
        What are these variables?
      </button>
      {open && (
        <div className="mt-3 p-4 bg-background border border-border rounded-xl space-y-3">
          <p className="text-xs font-semibold text-foreground">Variables are auto-filled for each lead at send time:</p>
          {VARIABLES.map(v => (
            <div key={v.key} className="flex gap-3">
              <code className="text-xs text-primary font-mono flex-shrink-0 pt-0.5 w-36">{v.key}</code>
              <div>
                <p className="text-xs text-muted-foreground leading-relaxed">{v.description}</p>
                <p className="text-xs text-muted-foreground/70 mt-0.5">e.g. <span className="text-muted-foreground">"{v.example}"</span></p>
              </div>
            </div>
          ))}
          <p className="text-xs text-amber-400/80 border-t border-border pt-3 flex items-start gap-1.5">
            <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
            If a variable can't be extracted (e.g. no "at" in headline), a sensible fallback is used.
          </p>
        </div>
      )}
    </div>
  )
}

// ── Test email modal ──────────────────────────────────────────────────────────
function TestEmailModal({ open, defaultCategory, templates, onClose }) {
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
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 py-4 border-b border-border flex-shrink-0">
          <DialogTitle>Send Test Email</DialogTitle>
          <DialogDescription>See exactly what the lead will receive</DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
              Send to (your email to test)
            </Label>
            <Input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
              Template Category
            </Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs text-muted-foreground font-medium uppercase tracking-wide block mb-2">
              Test Variable Values
            </Label>
            <div className="space-y-3">
              {VARIABLES.map(v => (
                <div key={v.key} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <code className="text-xs text-primary font-mono">{v.key}</code>
                    <span className="text-xs text-muted-foreground">— {v.description.split('(')[0].trim()}</span>
                  </div>
                  <Input
                    value={vars[v.label] || ''}
                    onChange={e => setVars(p => ({ ...p, [v.label]: e.target.value }))}
                  />
                </div>
              ))}
            </div>
          </div>

          <div>
            <button
              onClick={() => setShowPreview(p => !p)}
              className="text-xs text-primary hover:underline flex items-center gap-1"
            >
              {showPreview ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
              {showPreview ? 'Hide email preview' : 'Show email preview'}
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

          {status === 'success' && (
            <Alert className="border-emerald-500/30 bg-emerald-500/10">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              <AlertDescription className="text-emerald-400 font-medium">Email sent successfully! Check your inbox.</AlertDescription>
            </Alert>
          )}
          {status === 'error' && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{errMsg}</AlertDescription>
            </Alert>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border flex-shrink-0">
          <Button variant="outline" onClick={onClose}>Close</Button>
          <Button onClick={send} disabled={status === 'sending'} className="gap-2">
            {status === 'sending' && <Loader2 className="w-4 h-4 animate-spin" />}
            {status === 'sending' ? 'Sending...' : 'Send Test Email'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
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
      toast.success('Template saved')
    } catch (e) {
      toast.error('Save failed: ' + e.message)
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
        <Loader2 className="w-6 h-6 text-primary animate-spin" />
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col overflow-hidden p-6 gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-lg font-bold text-foreground">Email Templates</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Edit the personalised email for each lead category — variables highlight as you type</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" className="gap-2 border-amber-500/30 text-amber-400 hover:bg-amber-500/5 hover:text-amber-400" onClick={() => setShowTestModal(true)}>
            <Send className="w-4 h-4" />
            Test Email
          </Button>
          <Button variant="outline" className="gap-2" onClick={() => setShowPreview(p => !p)}>
            {showPreview ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            {showPreview ? 'Hide Preview' : 'Preview'}
          </Button>
          <Button onClick={save} disabled={!isDirty || saving} className="gap-2">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {saving ? 'Saving...' : isDirty ? 'Save Changes' : 'Saved'}
          </Button>
        </div>
      </div>

      {/* Category tabs */}
      <div className="flex flex-col gap-2 flex-shrink-0">
        <div className="flex gap-2 flex-wrap items-center">
          {[...SERVICE_CATEGORIES, 'Generic'].map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium border transition-all',
                activeCategory === cat ? CATEGORY_COLORS[cat] : 'text-muted-foreground border-transparent hover:text-foreground hover:bg-secondary'
              )}
            >
              {cat}
              {JSON.stringify(templates[cat]) !== JSON.stringify(saved[cat]) && (
                <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
              )}
            </button>
          ))}
        </div>
        <div className="flex gap-2 flex-wrap items-center">
          <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wide pr-1">Creative:</span>
          <button
            onClick={() => setActiveCategory(CREATIVE_MAIN)}
            title="Fallback used when the AI knows it's a creative-type ask but the industry doesn't fit any sub-category below"
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-semibold border transition-all',
              activeCategory === CREATIVE_MAIN ? CATEGORY_COLORS[CREATIVE_MAIN] : 'text-muted-foreground border-transparent hover:text-foreground hover:bg-secondary'
            )}
          >
            Main
            {JSON.stringify(templates[CREATIVE_MAIN]) !== JSON.stringify(saved[CREATIVE_MAIN]) && (
              <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
            )}
          </button>
          <Separator orientation="vertical" className="h-5" />
          {CREATIVE_SUBCATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium border transition-all',
                activeCategory === cat ? CATEGORY_COLORS[cat] : 'text-muted-foreground border-transparent hover:text-foreground hover:bg-secondary'
              )}
            >
              {cat.replace('Creative - ', '')}
              {JSON.stringify(templates[cat]) !== JSON.stringify(saved[cat]) && (
                <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Editor + preview */}
      <div className={cn('flex-1 grid gap-4 min-h-0', showPreview ? 'grid-cols-2' : 'grid-cols-1')}>
        {/* Editor column */}
        <div className="flex flex-col gap-3 min-h-0">
          <div className="flex-shrink-0 space-y-1.5">
            <Label className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
              Subject Line
            </Label>
            <div className="relative">
              <Input
                value={current.subject || ''}
                onChange={e => update('subject', e.target.value)}
                placeholder="Email subject..."
              />
              {current.subject && /\{\{[^}]+\}\}/.test(current.subject) && (
                <div className="absolute inset-0 px-3 pointer-events-none flex items-center">
                  <span className="text-sm">
                    {current.subject.split(/(\{\{[^}]+\}\})/g).map((part, i) =>
                      /^\{\{/.test(part)
                        ? <span key={i} className="text-primary">{part}</span>
                        : <span key={i} className="text-transparent">{part}</span>
                    )}
                  </span>
                </div>
              )}
            </div>
          </div>

          <div className="flex-1 flex flex-col min-h-0 gap-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
                Email Body
              </Label>
              {lastEdited[activeCategory] && (
                <span className="text-xs text-muted-foreground">Saved {lastEdited[activeCategory]}</span>
              )}
            </div>

            <div className="flex-1 min-h-0 bg-card border border-border rounded-lg overflow-hidden focus-within:border-primary/50 transition-colors flex flex-col">
              <HighlightTextarea
                value={current.body || ''}
                onChange={v => update('body', v)}
              />
            </div>
          </div>

          <div className="flex-shrink-0 space-y-2">
            <VarStatus body={current.body || ''} />
            <VariableReference />
          </div>
        </div>

        {/* Preview column */}
        {showPreview && (
          <div className="flex flex-col gap-3 min-h-0">
            <Label className="text-xs text-muted-foreground font-medium uppercase tracking-wide flex-shrink-0">
              Preview (with sample data)
            </Label>
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

      <TestEmailModal
        open={showTestModal}
        defaultCategory={activeCategory}
        templates={templates}
        onClose={() => setShowTestModal(false)}
      />
    </div>
  )
}
