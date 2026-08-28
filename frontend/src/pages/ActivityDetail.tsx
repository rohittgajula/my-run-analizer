import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api, type Activity } from '../lib/auth'

type Series = {
  points: Array<Record<string, number | null>>
  has_hr: boolean
  has_cadence: boolean
  has_altitude: boolean
}
import { RunTruth } from '../components/RunTruth'
import { RunTrace } from '../components/Charts'
import { Card } from '../components/Stat'
import { RunCoach } from '../components/RunCoach'
import { ZoneBar } from '../components/ZoneBar'
import { day, duration, km, metres, pace } from '../lib/format'

export default function ActivityDetail() {
  const { id } = useParams()
  const { data, isPending, error } = useQuery({
    queryKey: ['activity', id],
    queryFn: () => api<Activity>(`/activities/${id}/`),
  })
  const series = useQuery({
    queryKey: ['activity-series', id],
    queryFn: () => api<Series>(`/activities/${id}/series/`),
    retry: false,
  })

  if (isPending) return <main className="page"><p className="muted">Loading…</p></main>
  if (error) return <main className="page"><p className="bad">{String(error)}</p></main>
  if (!data) return null

  const segments = (data.segments ?? []).filter((s) => s.kind !== 'stop')

  return (
    <main className="page">
      <header className="header">
        <Link to="/activities" className="muted back">← Activities</Link>
        <h1>{day(data.local_date)}</h1>
        <p className="muted">
          {data.sport} · {duration(data.total_elapsed_s)} elapsed
        </p>
      </header>

      {data.metrics ? (
        <section className="card card-accent">
          <h2>What actually happened</h2>
          <RunTruth metrics={data.metrics} total={data.total_distance_m} />
        </section>
      ) : (
        <section className="card">
          <h2>Not segmented</h2>
          <p className="muted">
            {data.segmentation_version === null
              ? 'This activity has not been processed yet.'
              : 'Cadence here does not mean footsteps, so a run/walk split would be ' +
                'invented rather than measured. Nothing is shown rather than something wrong.'}
          </p>
        </section>
      )}

      {data.metrics?.time_in_zone && Object.keys(data.metrics.time_in_zone).length > 0 && (
        <Card
          title="Heart-rate zones"
          description="Aerobic base is built in Z1–Z2. Only Z2 is coloured, so one glance answers the question that matters: how much of this was actually easy?"
        >
          <ZoneBar totals={data.metrics.time_in_zone} />
        </Card>
      )}

      {data.metrics && <RunCoach id={Number(id)} />}

      {series.data && series.data.points.length > 0 && (
        <>
          <Card
            title="Pace"
            description="Shaded bands are your running blocks. Lower is faster — the axis is inverted so the line goes up when you speed up."
          >
            <RunTrace points={series.data.points} series="pace" blocks={data.segments} invert unit="/km" />
          </Card>

          {series.data.has_hr && (
            <Card
              title="Heart rate"
              description="Read it against the shaded run blocks: 160 bpm mid-block and 160 bpm while walking mean very different things."
            >
              <RunTrace points={series.data.points} series="hr" blocks={data.segments} unit="bpm" />
            </Card>
          )}

          {series.data.has_cadence && (
            <Card
              title="Cadence"
              description="Steps per minute, both legs. This is the signal that separates running from walking — the shaded bands are exactly where it crossed your threshold."
            >
              <RunTrace points={series.data.points} series="cadence" blocks={data.segments} unit="spm" />
            </Card>
          )}

          {series.data.has_altitude && (
            <Card title="Elevation" description="Hills explain a lot of what heart rate does.">
              <RunTrace points={series.data.points} series="altitude" blocks={data.segments} unit="m" />
            </Card>
          )}
        </>
      )}

      {segments.length > 0 && (
        <section className="card">
          <h2>Blocks</h2>
          {/* Scrolls rather than compresses: at 375px the columns otherwise
              collide and DISTANCE runs into PACE. */}
          <div className="table-scroll">
          <table className="blocks">
            <thead>
              <tr>
                <th>#</th>
                <th>Kind</th>
                <th>Time</th>
                <th>Distance</th>
                <th>Pace</th>
                <th>HR</th>
                <th title="Heart-rate recovery 60 s after the peak. Rises as fitness improves.">
                  HRR60
                </th>
              </tr>
            </thead>
            <tbody>
              {segments.map((segment) => (
                <tr key={segment.index} className={segment.kind === 'run' ? 'is-run' : ''}>
                  <td className="muted">{segment.index + 1}</td>
                  <td>{segment.kind}</td>
                  <td>{duration(segment.duration_s)}</td>
                  <td>{metres(segment.distance_m)}</td>
                  <td>{pace(segment.avg_pace_s_per_km)}</td>
                  <td>{segment.hr_avg ?? '—'}</td>
                  <td className={segment.hr_recovery_60s ? 'data' : 'muted'}>
                    {segment.hr_recovery_60s ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </section>
      )}

      <section className="card">
        <h2>As Garmin recorded it</h2>
        <dl className="stats">
          <div><dt>Distance</dt><dd>{km(data.total_distance_m)}</dd></div>
          <div><dt>Moving time</dt><dd>{duration(data.total_timer_s)}</dd></div>
          <div><dt>Avg HR</dt><dd>{data.avg_hr ?? '—'}</dd></div>
          <div><dt>Avg cadence</dt><dd>{data.avg_cadence_spm ? Math.round(data.avg_cadence_spm) : '—'}</dd></div>
        </dl>
      </section>
    </main>
  )
}
