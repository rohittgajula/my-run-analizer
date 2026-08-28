import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/auth'
import { Card, Stat } from '../components/Stat'
import { Races } from '../components/Races'

type Race = { id: number; name: string; date: string; distance_km: number; is_target: boolean }
type PlanToday = { date: string; mode: string; weeks_out: number | null; days_to_race: number | null; note: string; race: Race | null }
type PlanSession = {
  date: string
  kind: string
  run_minutes: number
  walk_minutes: number
  total_minutes: number
  target_run_m: number
  purpose: string
  effort: string
  continuous_target_s: number | null
}
type PlanWeek = {
  index: number
  weeks_out: number
  phase: string
  start_date: string
  planned_run_km: number
  continuous_target_s: number
  is_cutback: boolean
  sessions: PlanSession[]
}
type PlanData = {
  runway: string
  weeks_available: number
  peak_run_km: number
  ideal_peak_run_km: number
  reached_ideal_peak: boolean
  peak_continuous_s: number
  race_needs_continuous_s: number
  will_run_continuously: boolean
  warnings: string[]
  weeks: PlanWeek[]
}
type TodaySession = {
  mode: string
  session: PlanSession | null
  adjustment: { severity: string; changed: boolean; dropped: boolean; reasons: string[] } | null
}

type Prediction = {
  race: Race
  mode: string
  observations: number
  span_weeks: number
  confidence: string
  basis: string
  likely_finish_s: number | null
  range_s: [number, number] | null
  projected_longest_run_s: number | null
  projected_run_fraction: number | null
  what_would_change_it: string[]
}

const hms = (seconds: number) => {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.round(seconds % 60)
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`
}

const MODE_MEANING: Record<string, string> = {
  build: 'Building towards your target race.',
  race: 'Race day.',
  recovery: 'Recovering from a race. Nothing hard, however good you feel.',
  mini_taper: 'Short taper into a secondary race.',
  maintenance: 'Holding fitness. There is not enough time before the next race to build anything, and starting a ramp now would peak on a recovering body.',
  off_season: 'No race on the calendar.',
}

export default function Plan() {
  const today = useQuery({ queryKey: ['plan-today'], queryFn: () => api<PlanToday>('/plan/today/') })
  const predictions = useQuery({
    queryKey: ['predictions'],
    queryFn: () => api<Prediction[]>('/plan/predictions/'),
  })
  const weeks = useQuery({
    queryKey: ['plan-weeks'],
    queryFn: () => api<PlanData>('/plan/weeks/'),
    retry: false,
  })
  const session = useQuery({
    queryKey: ['plan-session'],
    queryFn: () => api<TodaySession>('/plan/session/'),
    retry: false,
  })

  return (
    <main className="page">
      <header className="header">
        <h1>
          Plan<span className="mark">.</span>
        </h1>
      </header>

      {session.data?.session && (
        <Card
          title="Today's session"
          description={session.data.session.purpose}
        >
          <div className="grid grid-4 tight">
            <Stat label="Session" value={session.data.session.kind.replace('_', '/').toLowerCase()} tone="data" />
            <Stat label="Running" value={session.data.session.run_minutes} unit="min" tone="data" />
            <Stat label="Walking" value={session.data.session.walk_minutes} unit="min" />
            <Stat label="Target" value={session.data.session.target_run_m} unit="m run" />
          </div>
          <p className="card-foot muted">{session.data.session.effort}</p>

          {/* Readiness notes sit OUTSIDE any collapsible or slide: on a critical day
              this says do not train hard, and that must not be behind a control
              nobody clicks. */}
          {session.data.adjustment?.changed && (
            <div className={`notice notice-${session.data.adjustment.severity}`}>
              <strong>
                {session.data.adjustment.dropped
                  ? 'Session dropped today'
                  : 'Eased from the planned session'}
              </strong>
              <ul>
                {session.data.adjustment.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      {today.data && (
        <Card title="Today" description={MODE_MEANING[today.data.mode]}>
          <div className="grid grid-4 tight">
            <Stat label="Mode" value={today.data.mode.replace('_', ' ')} tone="data" />
            <Stat label="Weeks out" value={today.data.weeks_out ?? '—'} />
            <Stat label="Days to race" value={today.data.days_to_race ?? '—'} />
            <Stat label="Race" value={today.data.race?.name ?? '—'} />
          </div>
          <p className="card-foot muted">{today.data.note}</p>
        </Card>
      )}

      <Races />

      {weeks.data && (
        <Card
          title="The build"
          description={`${weeks.data.weeks_available} weeks, ${weeks.data.runway.toLowerCase()} runway. Volume is RUNNING distance — ramping the logged total when most of it is walking prescribes a load you are not carrying.`}
        >
          <div className="grid grid-4 tight" style={{ marginBottom: '1.25rem' }}>
            <Stat label="Peak weekly running" value={weeks.data.peak_run_km.toFixed(1)} unit="km" />
            <Stat
              label="Longest block by race day"
              value={Math.round(weeks.data.peak_continuous_s / 60)}
              unit="min"
              tone="data"
              note="The number that decides whether race day holds together."
            />
            <Stat
              label="To run it unbroken"
              value={Math.round(weeks.data.race_needs_continuous_s / 60)}
              unit="min"
              note="At your current running pace."
            />
            <Stat
              label="Expected"
              value={weeks.data.will_run_continuously ? 'continuous' : 'run/walk'}
              tone={weeks.data.will_run_continuously ? 'ok' : 'neutral'}
            />
          </div>

          {weeks.data.warnings.map((warning) => (
            <p className="notice notice-caution" key={warning}>{warning}</p>
          ))}

          <div className="table-scroll">
            <table className="blocks weeks">
              <thead>
                <tr>
                  <th>Wk</th><th>Phase</th><th>Run km</th><th>Long block</th><th>Sessions</th>
                </tr>
              </thead>
              <tbody>
                {weeks.data.weeks.map((week) => (
                  <tr key={week.index} className={week.is_cutback ? '' : 'is-run'}>
                    <td className="muted">{week.index + 1}</td>
                    <td>{week.phase.toLowerCase()}</td>
                    <td className={week.is_cutback ? 'muted' : ''}>
                      {week.planned_run_km.toFixed(1)}
                      {week.is_cutback && <span className="unit">cutback</span>}
                    </td>
                    {/* The column that actually decides race day, so it carries the
                        data colour and the volume column does not. */}
                    <td className={week.is_cutback ? 'muted' : 'data'}>
                      {week.continuous_target_s
                        ? `${Math.round(week.continuous_target_s / 60)} min`
                        : '—'}
                    </td>
                    <td>{week.sessions.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {predictions.data?.map((prediction) => (
        <Card
          key={prediction.race.id}
          title={`Predicted finish — ${prediction.race.name}`}
          description={prediction.basis}
        >
          {prediction.likely_finish_s && prediction.range_s ? (
            <>
              <div className="grid grid-4 tight">
                <Stat label="Likely" value={hms(prediction.likely_finish_s)} tone="data" />
                <Stat label="Range" value={`${hms(prediction.range_s[0])} – ${hms(prediction.range_s[1])}`} />
                <Stat label="Confidence" value={prediction.confidence} />
                <Stat
                  label="Projected longest block"
                  value={prediction.projected_longest_run_s ? hms(prediction.projected_longest_run_s) : '—'}
                />
              </div>
              <p className="card-foot muted">
                A range, not a time. It narrows as more runs accumulate.
              </p>
            </>
          ) : (
            <>
              {/* Below the data threshold no number is shown at all. A point estimate
                  off a handful of runs would be fiction with a decimal point. */}
              <p>Not enough data yet to predict a finish time honestly.</p>
              <ul className="todo">
                {prediction.what_would_change_it.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
        </Card>
      ))}
    </main>
  )
}
