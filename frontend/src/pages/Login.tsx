import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext'
import { ApiError } from '../lib/auth'
import { Field } from '../components/Field'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(username, password)
      navigate('/', { replace: true })
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 429
          ? 'Too many attempts. Wait an hour and try again.'
          : caught instanceof ApiError
            ? caught.message
            : 'Could not reach the server.',
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
        <p className="muted">Sign in to your training.</p>
      </header>

      <form className="card" onSubmit={submit}>
        <Field label="Username">
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </Field>

        <Field label="Password">
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </Field>

        {error && (
          <p className="bad" role="alert">
            {error}
          </p>
        )}

        <button className="button button-block" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>

      <p className="muted centered">
        No account? <Link to="/register">Create one</Link>
      </p>
    </main>
  )
}
