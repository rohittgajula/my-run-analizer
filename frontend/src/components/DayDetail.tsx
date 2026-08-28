import { Link } from 'react-router-dom'
import { duration, km, metres, pace } from '../lib/format'

export type CalendarDay = {
  date: string
  mode: string
  phase: string | null
  is_today: boolean
  race: { name: string; distance_km: number } | null
  planned: {
    kind: string
    run_minutes: number
    walk_minutes: number
    target_run_m: number
    continuous_target_s: number | null
    purpose: string
    effort: string
    phase: string
    pace_s_per_km: number | null
    zone: string | null
    zone_label: string | null
    zone_low: number | null
    zone_high: number | null
    zone_purpose: string | null
  } | null
  activities: Array<{
    id: number
    sport: string
    logged_km: number
    run_m: number | null
    longest_run_s: number | null
  }>
  readiness: number | null
  has_note: boolean
}

const MODE_MEANING: Record<string, string> = {
  build: 'Building towards your target race.',
  race: 'Race day.',
  recovery: 'Recovering from a race. Nothing hard, however good you feel.',
  mini_taper: 'Short taper into a secondary race.',
  maintenance: 'Holding fitness — too close to the next race to build anything.',
  off_season: 'No race on the calendar.',
}

export function DayDetail({ day, onClose }: { day: CalendarDay; onClose: () => void }) {
  const p = day.planned
  const longDate = new Date(`${day.date}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'long', day: 'numeric', month: 'long',
  })

  return (
    <aside className="daydetail">
      <div className="daydetail-head">
        <div>
          <h2>{longDate}</h2>
          <p className="muted">
            {MODE_MEANING[day.mode] ?? day.mode}
            {day.phase && ` · ${day.phase.toLowerCase()} phase`}
          </p>
        </div>
        <button className="linkish" onClick={onClose} aria-label="Close">✕</button>
      </div>

      {day.race && (
        <div className="notice notice-caution">
          <strong>{day.race.name}</strong> — {day.race.distance_km} km.
        </div>
      )}

      {p ? (
        <section className="card">
          <h2>Prescribed</h2>
          <p className="coach-headline">
            {p.kind === 'WALK'
              ? `Walk ${Math.round(p.walk_minutes)} minutes.`
              : `Run ${metres(p.target_run_m)} — about ${Math.round(p.run_minutes)} minutes running` +
                (p.walk_minutes > 0 ? ` and ${Math.round(p.walk_minutes)} walking.` : '.')}
          </p>

          <dl className="stats">
            {p.pace_s_per_km && (
              <div>
                <dt>Target pace</dt>
                <dd className="data">{pace(p.pace_s_per_km)}<span className="unit">/km</span></dd>
              </div>
            )}
            {p.zone_low && (
              <div>
                <dt>{p.zone} {p.zone_label}</dt>
                <dd className="data">{p.zone_low}–{p.zone_high}<span className="unit">bpm</span></dd>
              </div>
            )}
            {p.continuous_target_s && (
              <div>
                <dt>Unbroken block</dt>
                <dd className="data">{duration(p.continuous_target_s)}</dd>
              </div>
            )}
            <div>
              <dt>Effort</dt>
              <dd style={{ fontSize: '0.95rem' }}>{p.effort}</dd>
            </div>
          </dl>

          <div className="coach-block">
            <h3>Why</h3>
            <p>{p.purpose}</p>
            {/* Pace and heart rate together: pace ignores hills and heat, heart rate
                lags by half a minute. Either alone is easy to run past. */}
            {p.zone_purpose && <p className="muted" style={{ marginTop: '0.6rem' }}>{p.zone_purpose}</p>}
          </div>
        </section>
      ) : (
        <section className="card">
          <h2>Nothing prescribed</h2>
          <p className="muted">
            Not a training day. An easy 20–30 minute walk is fine if you want to move.
          </p>
        </section>
      )}

      {day.activities.length > 0 && (
        <section className="card">
          <h2>What happened</h2>
          {day.activities.map((activity) => (
            <p key={activity.id}>
              <Link to={`/activities/${activity.id}`}>
                {activity.run_m ? (
                  <>
                    <span className="data">{metres(activity.run_m)}</span> run of{' '}
                    {km(activity.logged_km * 1000)}
                    {activity.longest_run_s ? ` · longest ${duration(activity.longest_run_s)}` : ''}
                  </>
                ) : (
                  <>{km(activity.logged_km * 1000)} {activity.sport}</>
                )}
              </Link>
            </p>
          ))}
        </section>
      )}

      {day.readiness != null && (
        <section className="card">
          <h2>Readiness that day</h2>
          <p className="stat-value">{day.readiness}<span className="unit">/100</span></p>
        </section>
      )}
    </aside>
  )
}
