import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext'
import { ApiError } from '../lib/auth'
import { DayPicker } from '../components/DayPicker'
import { Field } from '../components/Field'

/** Everything here has a working default. It exists so the defaults are seen, not guessed at. */
export default function Onboarding() {
  const { athlete, updateAthlete } = useAuth()
  const navigate = useNavigate()
  const [days, setDays] = useState(athlete?.available_days ?? {})
  const [longRunDay, setLongRunDay] = useState(athlete?.long_run_day ?? 6)
  const [displayName, setDisplayName] = useState(athlete?.display_name ?? '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const zone = athlete?.timezone ?? 'UTC'

  async function save() {
    setBusy(true)
    setError('')
    try {
      await updateAthlete({
        display_name: displayName,
        available_days: days,
        long_run_day: longRunDay,
        onboarding_complete: true,
      })
      navigate('/', { replace: true })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page page-narrow">
      <header className="header">
        <h1>A few basics</h1>
        <p className="muted">
          All of this is changeable later. It just makes the first plan sensible.
        </p>
      </header>

      <section className="card">
        <h2>You</h2>
        <Field label="Name">
          <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        </Field>
        <Field label="Timezone" hint="Detected from your browser. Change it in settings if wrong.">
          <input value={zone} readOnly />
        </Field>
      </section>

      <section className="card card-accent">
        <h2>When can you train</h2>
        <DayPicker
          value={days}
          onChange={setDays}
          longRunDay={longRunDay}
          onLongRunDayChange={setLongRunDay}
        />
      </section>

      {error && (
        <p className="bad" role="alert">
          {error}
        </p>
      )}

      <button className="button button-block" onClick={save} disabled={busy}>
        {busy ? 'Saving…' : 'Done'}
      </button>
    </main>
  )
}
