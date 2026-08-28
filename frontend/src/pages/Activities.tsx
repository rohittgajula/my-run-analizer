import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type Activity } from '../lib/auth'
import { day, duration, km, metres } from '../lib/format'

export default function Activities() {
  const { data, isPending, error } = useQuery({
    queryKey: ['activities'],
    queryFn: () => api<Activity[]>('/activities/'),
  })

  if (isPending) return <main className="page"><p className="muted">Loading…</p></main>
  if (error) return <main className="page"><p className="bad">{String(error)}</p></main>

  return (
    <main className="page">
      <header className="header">
        <h1>Activities</h1>
        <p className="muted">{data?.length ?? 0} imported from Garmin.</p>
      </header>

      <ul className="activity-list">
        {data?.map((activity) => {
          const m = activity.metrics
          return (
            <li key={activity.id}>
              <Link to={`/activities/${activity.id}`} className="activity-row">
                <div className="activity-when">
                  <span className="activity-date">{day(activity.local_date)}</span>
                  <span className="muted activity-sport">{activity.sport}</span>
                </div>

                <div className="activity-figures">
                  {m && m.run_block_count > 0 ? (
                    <>
                      <span className="truth-primary">{metres(m.run_distance_m)}</span>
                      <span className="muted"> run</span>
                      <span className="muted activity-secondary">
                        {' '}of {km(activity.total_distance_m)} · longest{' '}
                        {duration(m.longest_run_s)}
                      </span>
                    </>
                  ) : (
                    <>
                      <span>{km(activity.total_distance_m)}</span>
                      <span className="muted activity-secondary">
                        {' '}
                        {m ? 'no running' : 'not segmented'}
                      </span>
                    </>
                  )}
                </div>
              </Link>
            </li>
          )
        })}
      </ul>
    </main>
  )
}
