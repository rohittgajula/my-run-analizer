import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type Activity, type DailyMetrics } from '../lib/auth'
import { useAuth } from '../lib/AuthContext'
import { Card, Stat } from '../components/Stat'
import { Coach } from '../components/Coach'
import { JudgedBars, Ring, TrendLine } from '../components/Charts'
import { day, duration, metres } from '../lib/format'
import {
  READINESS_TONE, SLEEP_TONE, latest, mean, sleepHours, toSeries, versusBaseline,
} from '../lib/wellness'

type Plan = { mode: string; weeks_out: number | null; note: string; race: { name: string; date: string } | null }

const READINESS_MEANING: Record<string, string> = {
  ok: 'Your body is ready for a harder session if the plan calls for one.',
  mid: 'Enough for an easy session. Not a day to push.',
  low: 'Take it very easy or rest. Training hard on this rarely helps.',
}

export default function Home() {
  const { athlete } = useAuth()

  const wellness = useQuery({
    queryKey: ['wellness', 28],
    queryFn: () => api<DailyMetrics[]>('/wellness/?days=28'),
  })
  // /activities/ is paginated, so the response is {count, results}, not an array.
  // Asking for one page of runs is also all this card needs.
  const activities = useQuery({
    queryKey: ['recent-runs'],
    queryFn: () => api<{ results: Activity[] }>('/activities/?ran=true&page_size=5'),
  })
  const plan = useQuery({
    queryKey: ['plan-today'],
    queryFn: () => api<Plan>('/plan/today/'),
    retry: false,
  })

  const days = wellness.data ?? []
  const today = days[0]

  const readiness = today?.training_readiness ?? null
  const readinessBand = readiness == null ? null : readiness >= 75 ? 'ok' : readiness >= 40 ? 'mid' : 'low'

  const hrv = latest(days, 'hrv_overnight_avg')
  const hrvVs = versusBaseline(hrv, days.slice(1, 29).map((d) => d.hrv_overnight_avg))

  const sleep = sleepHours(today?.sleep_seconds ?? null)
  const sleepAvg = mean(days.map((d) => sleepHours(d.sleep_seconds)))
  const sleepDebt =
    sleepAvg != null && days.length >= 7
      ? days.slice(0, 7).reduce((total, d) => total + Math.max(8 - (sleepHours(d.sleep_seconds) ?? 8), 0), 0)
      : null

  const lastRun = activities.data?.results?.find((a) => a.metrics && a.metrics.run_block_count > 0)

  return (
    <main className="page">
      <header className="header">
        <h1>
          Today<span className="mark">.</span>
        </h1>
        <p className="muted">
          {plan.data?.race
            ? `${plan.data.mode.replace('_', ' ')} · ${plan.data.weeks_out ?? 0} weeks to ${plan.data.race.name}`
            : athlete?.display_name}
        </p>
      </header>

      {/* The coaching read comes first: a page of numbers with no interpretation is
          the thing this dashboard was, and the thing it should not be. */}
      <Coach />

      {/* Readiness next, because it is the only metric here that should change what
          you do in the next few hours. */}
      <div className="grid grid-4">
        <Card title="Training readiness">
          <div className="ring-row">
            <Ring value={readiness} tone={READINESS_TONE(readiness)} label="readiness" />
            <div>
              <div className="stat-value">{today?.training_readiness_level || '—'}</div>
              {readinessBand && <p className="stat-note">{READINESS_MEANING[readinessBand]}</p>}
            </div>
          </div>
        </Card>

        <Card title="Sleep">
          <div className="ring-row">
            <Ring value={today?.sleep_score ?? null} tone={SLEEP_TONE(today?.sleep_score ?? null)} label="sleep score" />
            <div>
              <div className="stat-value">
                {sleep != null ? sleep.toFixed(1) : '—'}
                <span className="unit">h</span>
              </div>
              <p className="stat-note">
                {sleepAvg != null ? `${sleepAvg.toFixed(1)} h average over 28 days` : 'No baseline yet'}
              </p>
            </div>
          </div>
        </Card>

        <Card title="HRV">
          <Stat
            label="Overnight average"
            value={hrv ?? '—'}
            unit={hrv ? 'ms' : undefined}
            tone="data"
            note={
              hrvVs
                ? `${hrvVs.delta >= 0 ? '+' : ''}${hrvVs.delta.toFixed(0)} ms against your 28-day average — ${
                    Math.abs(hrvVs.percent) < 5
                      ? 'in line with normal'
                      : hrvVs.delta > 0
                        ? 'a sign of good recovery'
                        : 'often follows poor sleep or a hard session'
                  }`
                : `Status: ${today?.hrv_status || 'unknown'}`
            }
          />
        </Card>

        <Card title="Acute load">
          <Stat
            label="7-day training load"
            value={today?.acute_load ?? '—'}
            tone="data"
            note={
              today?.training_status
                ? `Garmin calls this ${today.training_status.toLowerCase()}.`
                : 'Recent training load as Garmin computes it.'
            }
          />
        </Card>
      </div>

      <div className="grid grid-2">
        <Card
          title="Readiness, 28 days"
          description="Bars are coloured by what the score means for training, not by size: green is ready, amber is easy only, red is rest."
        >
          <JudgedBars
            data={toSeries(days, 'training_readiness')}
            dataKey="value"
            domain={[0, 100]}
            colour={(row) => READINESS_TONE((row.value as number) ?? null)}
          />
        </Card>

        <Card
          title="HRV, 28 days"
          description="Heart-rate variability overnight. The trend matters far more than any single night — a one-day dip usually reflects sleep or alcohol rather than fitness."
        >
          <TrendLine data={toSeries(days, 'hrv_overnight_avg')} dataKey="value" />
        </Card>

        <Card
          title="Sleep, 28 days"
          description={
            sleepDebt != null && sleepDebt > 4
              ? `Roughly ${sleepDebt.toFixed(0)} hours short of 8 h/night across the last week. That is the loudest signal in your data right now.`
              : 'Hours per night. Consistency matters more than any single long night.'
          }
        >
          <TrendLine
            data={toSeries(days, 'sleep_seconds').map((d) => ({
              date: d.date,
              value: d.value == null ? null : d.value / 3600,
            }))}
            dataKey="value"
            domain={[0, 10]}
            reference={8}
            referenceLabel="8 h"
          />
        </Card>

        <Card
          title="Resting heart rate, 28 days"
          description="Falls slowly as aerobic fitness improves. A sudden rise usually means fatigue, illness or a short night rather than lost fitness."
        >
          <TrendLine data={toSeries(days, 'resting_hr')} dataKey="value" />
        </Card>
      </div>

      {lastRun?.metrics && (
        <Card
          title="Last run"
          description="What you actually ran, not what the watch logged."
          wide
        >
          <div className="grid grid-4 tight">
            <Stat label="Date" value={day(lastRun.local_date)} />
            <Stat label="Run distance" value={metres(lastRun.metrics.run_distance_m)} tone="data" />
            <Stat label="Longest block" value={duration(lastRun.metrics.longest_run_s)} tone="data" />
            <Stat label="Blocks" value={lastRun.metrics.run_block_count} />
          </div>
          <p className="card-foot">
            <Link to={`/activities/${lastRun.id}`}>See the full breakdown →</Link>
          </p>
        </Card>
      )}
    </main>
  )
}
