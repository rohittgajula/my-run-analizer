import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../lib/auth'
import { DayDetail, type CalendarDay } from '../components/DayDetail'
import { duration } from '../lib/format'

type Day = CalendarDay

type Month = { month: string; leading_blanks: number; days: Day[] }

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const MODE_LABEL: Record<string, string> = {
  build: 'Build',
  race: 'Race',
  recovery: 'Recovery',
  mini_taper: 'Taper',
  maintenance: 'Maintenance',
  off_season: 'Off season',
}

function shift(month: string, by: number): string {
  const [year, m] = month.split('-').map(Number)
  const date = new Date(year, m - 1 + by, 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

export default function Calendar() {
  const [month, setMonth] = useState<string | null>(null)
  const [selected, setSelected] = useState<Day | null>(null)
  const { data, isPending } = useQuery({
    queryKey: ['calendar', month],
    queryFn: () => api<Month>(`/plan/calendar/${month ? `?month=${month}` : ''}`),
  })

  if (isPending) return <main className="page"><p className="muted">Loading…</p></main>
  if (!data) return null

  const title = new Date(`${data.month}-01T00:00:00`).toLocaleDateString(undefined, {
    month: 'long', year: 'numeric',
  })

  return (
    <main className="page">
      <header className="header">
        <h1>
          Calendar<span className="mark">.</span>
        </h1>
        <p className="muted">
          What each day is for, what was planned, and what actually happened.
        </p>
      </header>

      <div className="month-nav">
        <button className="filter" onClick={() => setMonth(shift(data.month, -1))}>←</button>
        <strong>{title}</strong>
        <button className="filter" onClick={() => setMonth(shift(data.month, 1))}>→</button>
      </div>

      <div className="cal">
        {WEEKDAYS.map((label) => (
          <div key={label} className="cal-head">{label}</div>
        ))}
        {Array.from({ length: data.leading_blanks }).map((_, index) => (
          <div key={`blank-${index}`} className="cal-cell cal-blank" />
        ))}

        {data.days.map((cell) => (
          <button
              key={cell.date}
              type="button"
              onClick={() => setSelected(cell)}
              className={`cal-cell mode-${cell.mode} ${cell.is_today ? 'cal-today' : ''} ${
                selected?.date === cell.date ? 'cal-selected' : ''
              }`}
            >
              <div className="cal-top">
                <span className="cal-date">{Number(cell.date.slice(-2))}</span>
                {cell.readiness != null && (
                  <span
                    className={`cal-readiness ${cell.readiness < 25 ? 'bad' : cell.readiness < 45 ? 'warn' : ''}`}
                    title={`Training readiness ${cell.readiness}`}
                  >
                    {cell.readiness}
                  </span>
                )}
              </div>

              {cell.race && <div className="cal-race">{cell.race.distance_km}K</div>}

              {/* Planned first, then actual underneath it — the comparison is the
                  point of a calendar, and stacking them makes it readable at a glance. */}
              {cell.planned && (
                <div className="cal-planned">
                  {cell.planned.kind.replace('_', '/').toLowerCase()}
                  <span className="muted"> {Math.round(cell.planned.run_minutes)}′</span>
                </div>
              )}

              {cell.activities.map((activity) => (
                <span key={activity.id} className="cal-actual">
                  {activity.run_m ? (
                    <>
                      <span className="data">{activity.run_m} m</span>
                      {activity.longest_run_s ? (
                        <span className="muted"> · {duration(activity.longest_run_s)}</span>
                      ) : null}
                    </>
                  ) : (
                    <span className="muted">{activity.logged_km} km {activity.sport}</span>
                  )}
                </span>
              ))}

            {cell.has_note && <span className="cal-note" title="You wrote something">•</span>}
          </button>
        ))}
      </div>

      {selected && <DayDetail day={selected} onClose={() => setSelected(null)} />}

      <div className="legend">
        {Object.entries(MODE_LABEL).map(([mode, label]) => (
          <span key={mode} className={`legend-item mode-${mode}`}>{label}</span>
        ))}
      </div>
    </main>
  )
}
