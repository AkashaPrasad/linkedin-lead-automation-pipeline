import { useEffect, useRef, useState } from 'react'
import { Search, CheckCircle2, Mail, Send } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

function AnimatedNumber({ value }) {
  const [display, setDisplay] = useState(0)
  const prevRef = useRef(0)

  useEffect(() => {
    const from = prevRef.current
    const to = value
    if (from === to) return
    prevRef.current = to

    const steps = 20
    const increment = (to - from) / steps
    let current = from
    let step = 0

    const id = setInterval(() => {
      step++
      current += increment
      if (step >= steps) {
        setDisplay(to)
        clearInterval(id)
      } else {
        setDisplay(Math.round(current))
      }
    }, 25)

    return () => clearInterval(id)
  }, [value])

  return <span>{display.toLocaleString()}</span>
}

const CARDS = [
  { key: 'scraped', label: 'Posts Scraped', icon: Search, color: 'text-primary' },
  { key: 'real', label: 'Real Leads', icon: CheckCircle2, color: 'text-emerald-400' },
  { key: 'enriched', label: 'Emails Found', icon: Mail, color: 'text-amber-400' },
  { key: 'sent', label: 'Emails Sent', icon: Send, color: 'text-sky-400' },
]

export default function StatsBar({ stats }) {
  return (
    <div className="grid grid-cols-4 gap-4">
      {CARDS.map(card => {
        const Icon = card.icon
        return (
          <Card key={card.key} className="border-border/80 bg-card transition-colors hover:border-primary/30">
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <div className={cn('flex items-center justify-center w-8 h-8 rounded-lg bg-secondary', card.color)}>
                  <Icon className="w-4 h-4" strokeWidth={2} />
                </div>
                <span className="text-xs text-muted-foreground font-medium uppercase tracking-wide">{card.label}</span>
              </div>
              <div className={cn('text-3xl font-bold tabular-nums', card.color)}>
                <AnimatedNumber value={stats[card.key] || 0} />
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
