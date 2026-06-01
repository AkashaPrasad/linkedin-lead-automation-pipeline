import { useEffect, useRef, useState } from 'react'

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
  { key: 'scraped', label: 'Posts Scraped', icon: '🔍', color: 'text-purple-light', border: 'border-purple-primary/20' },
  { key: 'real', label: 'Real Leads', icon: '✅', color: 'text-green-accent', border: 'border-green-accent/20' },
  { key: 'enriched', label: 'Emails Found', icon: '✉', color: 'text-amber-accent', border: 'border-amber-accent/20' },
  { key: 'sent', label: 'Emails Sent', icon: '🚀', color: 'text-blue-400', border: 'border-blue-400/20' },
]

export default function StatsBar({ stats }) {
  return (
    <div className="grid grid-cols-4 gap-4">
      {CARDS.map(card => (
        <div
          key={card.key}
          className={`bg-bg-secondary rounded-xl p-4 border ${card.border} card-border`}
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-lg">{card.icon}</span>
            <span className="text-xs text-text-muted font-medium uppercase tracking-wide">{card.label}</span>
          </div>
          <div className={`text-3xl font-bold ${card.color}`}>
            <AnimatedNumber value={stats[card.key] || 0} />
          </div>
        </div>
      ))}
    </div>
  )
}
