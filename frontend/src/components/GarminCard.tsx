import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError, api, json } from '../lib/auth'
import { useAuth } from '../lib/AuthContext'
import { Field } from './Field'

type Status = { connected: boolean; name: string; error: string; last_sync: string | null }
type SyncResult = { imported: number; skipped: number; failed: number; errors: string[] }

export function GarminCard() {
  const client = useQueryClient()
  const { athlete } = useAuth()
  const [showForm, setShowForm] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [sync, setSync] = useState<SyncResult | null>(null)

  const status = useQuery({
    queryKey: ['garmin-status'],
    queryFn: () => api<Status>('/garmin/status/'),
    retry: false,
  })

  const connect = useMutation({
    mutationFn: () => api<Status>('/garmin/connect/', { method: 'POST', ...json({ email, password }) }),
    onSuccess: () => {
      // Held only long enough to send. Nothing keeps it after that.
      setPassword('')
      setEmail('')
      setShowForm(false)
      setError('')
      client.invalidateQueries({ queryKey: ['garmin-status'] })
    },
    onError: (caught) =>
      setError(caught instanceof ApiError ? caught.message : 'Could not reach the server.'),
  })

  const disconnect = useMutation({
    mutationFn: () => api('/garmin/disconnect/', { method: 'POST' }),
    onSuccess: () => {
      setSync(null)
      client.invalidateQueries({ queryKey: ['garmin-status'] })
    },
  })

  const runSync = useMutation({
    mutationFn: () => api<SyncResult>('/garmin/sync/', { method: 'POST', ...json({ limit: 20 }) }),
    onSuccess: (result) => {
      setSync(result)
      client.invalidateQueries({ queryKey: ['garmin-status'] })
    },
    onError: (caught) =>
      setError(caught instanceof ApiError ? caught.message : 'Sync failed.'),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    connect.mutate()
  }

  const connected = status.data?.connected

  return (
    <section className="card">
      <h2>Garmin</h2>

      {status.isPending && <p className="muted">Checking…</p>}

      {status.data && !connected && !showForm && (
        <>
          <p className="muted">
            Not connected. Activities are downloaded as original <code>.fit</code> files,
            which carry the per-second data Garmin's summary leaves out.
          </p>
          <button className="button" onClick={() => setShowForm(true)}>
            Connect Garmin
          </button>
        </>
      )}

      {showForm && (
        <form onSubmit={submit}>
          <p className="muted">
            Your password is used once to obtain a session token, then discarded. It is
            never stored, logged, or sent anywhere but Garmin.
          </p>

          <Field label="Garmin email">
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="off"
              required
            />
          </Field>

          <Field label="Garmin password">
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="off"
              required
            />
          </Field>

          {error && (
            <p className="bad" role="alert">
              {error}
            </p>
          )}

          <div className="row row-end">
            <button
              type="button"
              className="linkish"
              onClick={() => {
                setShowForm(false)
                setPassword('')
                setError('')
              }}
            >
              Cancel
            </button>
            <button className="button" disabled={connect.isPending}>
              {connect.isPending ? 'Connecting…' : 'Connect'}
            </button>
          </div>
        </form>
      )}

      {connected && (
        <>
          <ul className="checks">
            <li>
              <span className="dot dot-ok" /> Connected{status.data?.name ? ` as ${status.data.name}` : ''}
            </li>
          </ul>
          <p className="muted">
            {status.data?.last_sync
              ? `Last sync ${new Date(status.data.last_sync).toLocaleString()}`
              : 'Never synced.'}
          </p>

          {sync && (
            <p className={sync.failed ? 'bad' : 'muted'}>
              {sync.imported} imported · {sync.skipped} already had · {sync.failed} failed
              {sync.imported === 0 && sync.failed === 0 && ' — nothing new, which is what a re-sync should say'}
            </p>
          )}
          {sync?.errors?.map((line) => (
            <p className="bad" key={line}>
              {line}
            </p>
          ))}
          {error && <p className="bad">{error}</p>}

          <div className="row row-end">
            <button className="linkish" onClick={() => disconnect.mutate()}>
              Disconnect
            </button>
            <button className="button" onClick={() => runSync.mutate()} disabled={runSync.isPending}>
              {runSync.isPending ? 'Syncing…' : 'Sync now'}
            </button>
          </div>
        </>
      )}

      {/* Only worth showing when we BELIEVED we were connected: a token that exists
          and no longer works is real information. "No session found" for someone who
          has never connected is just the empty state restated. */}
      {athlete?.garmin_connected && !connected && status.data?.error && !showForm && (
        <p className="bad">Connection stopped working — {status.data.error}</p>
      )}
    </section>
  )
}
