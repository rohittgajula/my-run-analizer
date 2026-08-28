import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/auth'
import { Card, Stat } from '../components/Stat'

type Race = { id: number; name: string; date: string; distance_km: number; is_target: boolean }
type PlanToday = { date: string; mode: string; weeks_out: number | null; days_to_race: number | null; note: string; race: Race | null }
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
  const races = useQuery({ queryKey: ['races'], queryFn: () => api<Race[]>('/races/') })
  const predictions = useQuery({
    queryKey: ['predictions'],
    queryFn: () => api<Prediction[]>('/plan/predictions/'),
  })

  return (
    <main className="page">
      <header className="header">
        <h1>
          Plan<span className="mark">.</span>
        </h1>
      </header>

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

      <Card title="Races" description="One target race anchors the plan. Others get their own taper and recovery without moving it.">
        {races.data?.length ? (
          <ul className="racelist">
            {races.data.map((race) => (
              <li key={race.id}>
                <span>
                  <strong>{race.name}</strong>
                  {race.is_target && <span className="pill">target</span>}
                </span>
                <span className="muted">
                  {new Date(`${race.date}T00:00:00`).toLocaleDateString(undefined, {
                    day: 'numeric', month: 'long', year: 'numeric',
                  })}{' '}
                  · {race.distance_km} km
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No races yet.</p>
        )}
      </Card>

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
