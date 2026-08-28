import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError, api, json } from '../lib/auth'
import { Card } from './Stat'
import { Field } from './Field'

export type Race = {
  id: number
  name: string
  date: string
  distance_km: number
  is_target: boolean
  notes: string
}

const DISTANCES = [
  { label: '5K', km: 5 },
  { label: '10K', km: 10 },
  { label: 'Half', km: 21.1 },
  { label: 'Marathon', km: 42.2 },
]

/**
 * Everything downstream of a race is computed on read — the plan, the mode for
 * today, the prediction — so changing a date here changes all of it. The only work
 * is invalidating the queries that hold the old answer.
 */
const DEPENDENT_QUERIES = [
  ['races'], ['plan-weeks'], ['plan-today'], ['plan-session'],
  ['predictions'], ['calendar'], ['coach-guidance'],
]

const blank = { name: '', date: '', distance_km: 10, is_target: false }

export function Races() {
  const client = useQueryClient()
  const [editing, setEditing] = useState<Race | typeof blank | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})

  const races = useQuery({ queryKey: ['races'], queryFn: () => api<Race[]>('/races/') })

  const invalidate = () => {
    for (const key of DEPENDENT_QUERIES) client.invalidateQueries({ queryKey: key })
    setEditing(null)
    setErrors({})
  }

  const save = useMutation({
    mutationFn: (race: Race | typeof blank) => {
      const body = {
        name: race.name,
        date: race.date,
        distance_km: race.distance_km,
        is_target: race.is_target,
      }
      return 'id' in race
        ? api<Race>(`/races/${race.id}/`, { method: 'PATCH', ...json(body) })
        : api<Race>('/races/', { method: 'POST', ...json(body) })
    },
    onSuccess: invalidate,
    onError: (caught) =>
      setErrors(caught instanceof ApiError ? caught.fieldErrors() : { detail: 'Could not save.' }),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api(`/races/${id}/`, { method: 'DELETE' }),
    onSuccess: invalidate,
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    if (editing) save.mutate(editing)
  }

  return (
    <Card
      title="Races"
      description="One target race anchors the plan. Others get their own short taper and recovery without moving it. Changing a date here rebuilds the plan, the calendar and the prediction."
    >
      {races.data?.length ? (
        <ul className="racelist">
          {races.data.map((race) => (
            <li key={race.id}>
              <span>
                <strong>{race.name}</strong>
                {race.is_target && <span className="pill">target</span>}
              </span>
              <span className="race-meta">
                <span className="muted">
                  {new Date(`${race.date}T00:00:00`).toLocaleDateString(undefined, {
                    day: 'numeric', month: 'short', year: 'numeric',
                  })}{' '}
                  · {race.distance_km} km
                </span>
                <button className="linkish" onClick={() => setEditing(race)}>Edit</button>
                <button className="linkish bad" onClick={() => remove.mutate(race.id)}>Remove</button>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No races yet. Add one and the plan builds towards it.</p>
      )}

      {editing ? (
        <form className="race-form" onSubmit={submit}>
          <Field label="Name" error={errors.name}>
            <input
              value={editing.name}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
              placeholder="Bajaj Pune 10K"
              required
            />
          </Field>

          <div className="row">
            <Field label="Date" error={errors.date}>
              <input
                type="date"
                value={editing.date}
                onChange={(e) => setEditing({ ...editing, date: e.target.value })}
                required
              />
            </Field>
            <Field label="Distance" error={errors.distance_km}>
              <select
                value={editing.distance_km}
                onChange={(e) => setEditing({ ...editing, distance_km: Number(e.target.value) })}
              >
                {DISTANCES.map((d) => (
                  <option key={d.km} value={d.km}>{d.label}</option>
                ))}
              </select>
            </Field>
          </div>

          <label className="checkline">
            <input
              type="checkbox"
              checked={editing.is_target}
              onChange={(e) => setEditing({ ...editing, is_target: e.target.checked })}
            />
            <span>
              This is the race the plan builds towards
              {errors.is_target && <span className="field-error">{errors.is_target}</span>}
            </span>
          </label>

          {errors.detail && <p className="bad">{errors.detail}</p>}

          <div className="row row-end">
            <button type="button" className="linkish" onClick={() => setEditing(null)}>Cancel</button>
            <button className="button" disabled={save.isPending}>
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      ) : (
        <p className="card-foot">
          <button className="linkish" onClick={() => setEditing({ ...blank })}>+ Add a race</button>
        </p>
      )}
    </Card>
  )
}
