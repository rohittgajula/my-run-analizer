import type { ReactNode } from 'react'

/**
 * One number with its label and, where it helps, a plain-language reading.
 *
 * The `note` is the point. A bare "47 ms" tells a beginner nothing; "above your
 * 28-day average" tells them what to do with it. Anything the data cannot support
 * is left out rather than filled with a guess.
 */
export function Stat({
  label, value, unit, note, tone = 'neutral', children,
}: {
  label: string
  value: ReactNode
  unit?: string
  note?: ReactNode
  tone?: 'neutral' | 'data' | 'ok' | 'warn' | 'bad'
  children?: ReactNode
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className={`stat-value tone-${tone}`}>
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      {note && <div className="stat-note">{note}</div>}
      {children}
    </div>
  )
}

export function Card({
  title, description, children, wide,
}: {
  title: string
  description?: ReactNode
  children: ReactNode
  wide?: boolean
}) {
  return (
    <section className={`card ${wide ? 'card-wide' : ''}`}>
      <h2>{title}</h2>
      {description && <p className="card-desc">{description}</p>}
      {children}
    </section>
  )
}
