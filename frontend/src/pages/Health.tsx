import { useQuery } from '@tanstack/react-query'
import { api, type DailyMetrics } from '../lib/auth'
import { Card, Stat } from '../components/Stat'
import { JudgedBars, TrendArea, TrendLine } from '../components/Charts'
import { latest, mean, sleepHours, toSeries } from '../lib/wellness'

const STRESS_TONE = (v: number | null) =>
  v == null ? '#5a5a66' : v < 25 ? '#3ddc97' : v < 50 ? '#ffb800' : '#ff4d6d'

export default function Health() {
  const { data, isPending, error } = useQuery({
    queryKey: ['wellness', 90],
    queryFn: () => api<DailyMetrics[]>('/wellness/?days=90'),
  })

  if (isPending) return <main className="page"><p className="muted">Loading…</p></main>
  if (error) return <main className="page"><p className="bad">{String(error)}</p></main>

  const days = data ?? []
  const today = days[0]
  const avgSleep = mean(days.map((d) => sleepHours(d.sleep_seconds)))
  const avgHrv = mean(days.map((d) => d.hrv_overnight_avg))
  const avgRhr = mean(days.map((d) => d.resting_hr))
  const vo2 = latest(days, 'vo2max')

  return (
    <main className="page">
      <header className="header">
        <h1>
          Health<span className="mark">.</span>
        </h1>
        <p className="muted">
          {days.length} days from Garmin. These are Garmin's own measurements, shown as
          trends rather than re-computed.
        </p>
      </header>

      <div className="grid grid-4">
        <Stat label="Sleep average" value={avgSleep?.toFixed(1) ?? '—'} unit="h" />
        <Stat label="HRV average" value={avgHrv?.toFixed(0) ?? '—'} unit="ms" tone="data" />
        <Stat label="Resting HR" value={avgRhr?.toFixed(0) ?? '—'} unit="bpm" />
        <Stat
          label="VO₂ max"
          value={vo2?.toFixed(1) ?? '—'}
          note={vo2 ? "Garmin's estimate, not a lab test." : undefined}
        />
      </div>

      <div className="grid grid-2">
        <Card
          title="Body Battery range"
          description="How much the day drained you. A high that never reaches the previous morning's is the clearest sign of accumulating fatigue."
        >
          <TrendArea data={toSeries(days, 'body_battery_high')} dataKey="value" domain={[0, 100]} />
        </Card>

        <Card
          title="Stress"
          description="Garmin's all-day average. Coloured by band rather than by height, so a red bar means something regardless of the scale."
        >
          <JudgedBars
            data={toSeries(days, 'stress_avg')}
            dataKey="value"
            domain={[0, 100]}
            colour={(row) => STRESS_TONE((row.value as number) ?? null)}
          />
        </Card>

        <Card
          title="Acute training load"
          description="Rolling recent load. Rising quickly is the pattern that precedes injury far more often than any single hard session."
        >
          <TrendLine data={toSeries(days, 'acute_load')} dataKey="value" />
        </Card>

        <Card
          title="Steps"
          description="Everything outside training still counts as load on the legs."
        >
          <TrendLine data={toSeries(days, 'steps')} dataKey="value" />
        </Card>

        <Card
          title="Respiration"
          description="Waking average, breaths per minute. Elevated for several days can precede illness."
        >
          <TrendLine data={toSeries(days, 'respiration_avg')} dataKey="value" />
        </Card>

        <Card
          title="Deep and REM sleep"
          description="Deep sleep drives physical recovery. The total matters less than whether it is there at all."
        >
          <TrendLine
            data={toSeries(days, 'deep_sleep_seconds').map((d) => ({
              date: d.date,
              value: d.value == null ? null : d.value / 60,
            }))}
            dataKey="value"
          />
        </Card>
      </div>

      {today?.training_status && (
        <Card title="Garmin's read" description="Shown as context. Nothing in this app's planning depends on it.">
          <div className="grid grid-4 tight">
            <Stat label="Training status" value={today.training_status} />
            <Stat label="HRV status" value={today.hrv_status || '—'} />
            <Stat label="Readiness" value={today.training_readiness_level || '—'} />
            <Stat label="Acute load" value={today.acute_load ?? '—'} />
          </div>
        </Card>
      )}
    </main>
  )
}
