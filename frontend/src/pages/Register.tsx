import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext'
import { ApiError } from '../lib/auth'
import { Field } from '../components/Field'

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ username: '', email: '', password: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)

  const set = (key: keyof typeof form) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [key]: event.target.value }))

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setErrors({})
    try {
      await register({
        ...form,
        // Seeded from the browser so a new athlete is not silently on UTC, which
        // would shift every date in the app by hours.
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      })
      navigate('/onboarding', { replace: true })
    } catch (caught) {
      setErrors(
        caught instanceof ApiError
          ? caught.status === 429
            ? { detail: 'Too many sign-ups from this network. Try again later.' }
            : caught.fieldErrors()
          : { detail: 'Could not reach the server.' },
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page page-narrow">
      <header className="header">
        <h1>
          Run Analize<span className="mark">r</span>
        </h1>
        <p className="muted">Create your account.</p>
      </header>

      <form className="card" onSubmit={submit}>
        <Field label="Username" error={errors.username}>
          <input value={form.username} onChange={set('username')} autoComplete="username" autoFocus required />
        </Field>

        <Field label="Email" error={errors.email} hint="Optional.">
          <input type="email" value={form.email} onChange={set('email')} autoComplete="email" />
        </Field>

        <Field
          label="Password"
          error={errors.password}
          hint="At least 8 characters, and not something common."
        >
          <input
            type="password"
            value={form.password}
            onChange={set('password')}
            autoComplete="new-password"
            required
          />
        </Field>

        {errors.detail && (
          <p className="bad" role="alert">
            {errors.detail}
          </p>
        )}

        <button className="button button-block" disabled={busy}>
          {busy ? 'Creating…' : 'Create account'}
        </button>
      </form>

      <p className="muted centered">
        Already have one? <Link to="/login">Sign in</Link>
      </p>
    </main>
  )
}
