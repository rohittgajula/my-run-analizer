import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api, type Activity } from '../lib/auth'
import { RunTruth } from '../components/RunTruth'
import { day, duration, km, metres, pace } from '../lib/format'

export default function ActivityDetail() {
  const { id } = useParams()
  const { data, isPending, error } = useQuery({
    queryKey: ['activity', id],
    queryFn: () => api<Activity>(`/activities/${id}/`),
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
