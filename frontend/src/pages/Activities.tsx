import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Activity } from '../lib/auth'
import { day, duration, km, metres } from '../lib/format'

type Page = { count: number; next: string | null; previous: string | null; results: Activity[] }
type Facets = {
  sports: Array<{ value: string; count: number }>
  with_running: number
  total: number
  earliest: string | null
}

export default function Activities() {
  const [page, setPage] = useState(1)
  const [sport, setSport] = useState<string | null>(null)
  const [ranOnly, setRanOnly] = useState(false)

  const facets = useQuery({ queryKey: ['facets'], queryFn: () => api<Facets>('/activities/facets/') })

  const query = new URLSearchParams({ page: String(page) })
  if (sport) query.set('sport', sport)
  if (ranOnly) query.set('ran', 'true')

  const { data, isPending, error } = useQuery({
    queryKey: ['activities', page, sport, ranOnly],
    queryFn: () => api<Page>(`/activities/?${query}`),
    // Holds the previous page on screen while the next loads. Without it the list
    // empties, the page collapses to nothing and springs back.
    placeholderData: keepPreviousData,
  })

  const reset = (fn: () => void) => () => {
    fn()
    setPage(1)   // a filter change invalidates the page number
  }

  const pages = data ? Math.ceil(data.count / 20) : 1

  return (
    <main className="page">
      <header className="header">
        <h1>
          Activities<span className="mark">.</span>
        </h1>
        <p className="muted">
          {data?.count ?? 0} of {facets.data?.total ?? 0}
          {facets.data?.earliest && ` · back to ${day(facets.data.earliest)}`}
        </p>
      </header>

      <div className="filters">
        <button
          className={`filter ${!sport && !ranOnly ? 'filter-on' : ''}`}
          onClick={reset(() => {
            setSport(null)
            setRanOnly(false)
          })}
        >
          All
        </button>
        <button
          className={`filter ${ranOnly ? 'filter-on' : ''}`}
          onClick={reset(() => {
            setRanOnly(!ranOnly)
            setSport(null)
          })}
          title="Activities containing actual running, which is not the same as ones Garmin labelled running"
        >
          Actually ran <span className="filter-count">{facets.data?.with_running ?? 0}</span>
        </button>
        {facets.data?.sports.map((entry) => (
          <button
            key={entry.value}
            className={`filter ${sport === entry.value ? 'filter-on' : ''}`}
            onClick={reset(() => {
              setSport(sport === entry.value ? null : entry.value)
              setRanOnly(false)
            })}
          >
            {entry.value} <span className="filter-count">{entry.count}</span>
          </button>
        ))}
      </div>

      {error && <p className="bad">{String(error)}</p>}
      {isPending && !data && <p className="muted">Loading…</p>}

      <ul className="activity-list">
        {data?.results.map((activity) => {
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
                        {' '}of {km(activity.total_distance_m)} · longest {duration(m.longest_run_s)}
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

      {data && data.count === 0 && <p className="muted">Nothing matches that filter.</p>}

      {pages > 1 && (
        <nav className="pager">
          <button className="filter" disabled={!data?.previous} onClick={() => setPage((p) => p - 1)}>
            ← Newer
          </button>
          <span className="muted">
            Page {page} of {pages}
          </span>
          <button className="filter" disabled={!data?.next} onClick={() => setPage((p) => p + 1)}>
            Older →
          </button>
        </nav>
      )}
    </main>
  )
}
