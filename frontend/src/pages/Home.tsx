import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Health } from '../api'
import { installState, promptInstall } from '../lib/install'

function InstallCard() {
  const [state, setState] = useState(installState)

  if (state.kind === 'installed') return null

  return (
    <section className="card card-accent">
      <h2>Install on your phone</h2>
      {state.kind === 'prompt-ready' && (
        <>
          <p>This app can be installed to your home screen and opened without browser chrome.</p>
          <button
            className="button"
            onClick={async () => {
              await promptInstall()
              setState(installState())
            }}
          >
            Install
          </button>
        </>
      )}
      {state.kind === 'ios-safari' && (
        <p>
          Tap the <strong>Share</strong> button, then <strong>Add to Home Screen</strong>.
        </p>
      )}
      {state.kind === 'ios-other-browser' && (
        <p>
          iOS only allows installing from Safari. Open this page in Safari, then use{' '}
          <strong>Share → Add to Home Screen</strong>.
        </p>
      )}
      {state.kind === 'unsupported' && (
        <p className="muted">
          Installing needs Chrome on Android or Safari on iOS. Everything works in this
          browser regardless.
        </p>
      )}
    </section>
  )
}

function Dot({ ok }: { ok: boolean }) {
  return <span className={ok ? 'dot dot-ok' : 'dot dot-bad'} aria-hidden="true" />
}

export default function Home() {
  const { data, error, isPending } = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/health/'),
    refetchInterval: 15_000,
    retry: false,
  })

  return (
    <main className="page">
      <header className="header">
        <h1>
          Run Analize<span className="mark">r</span>
        </h1>
        <p className="muted">
          Race-date-driven coaching on Garmin data. Milestone&nbsp;0 — scaffold.
        </p>
      </header>

      <section className="card">
        <h2>Backend</h2>
        {isPending && <p className="muted">Checking…</p>}
        {error && <p className="bad">Unreachable — {String(error.message)}</p>}
        {data && (
          <ul className="checks">
            <li>
              <Dot ok={data.db} /> PostgreSQL
            </li>
            <li>
              <Dot ok={data.redis} /> Redis
            </li>
          </ul>
        )}
      </section>

      <InstallCard />

      <section className="card">
        <h2>Next</h2>
        <p className="muted">
          M1 — data model and the Garmin transplant. See <code>docs/ROADMAP.md</code>.
        </p>
      </section>
    </main>
  )
}
