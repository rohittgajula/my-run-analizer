import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../lib/auth'
import { useAuth } from '../lib/AuthContext'
import { installState, promptInstall } from '../lib/install'
import { GarminCard } from '../components/GarminCard'

type Health = { status: string; db: boolean; redis: boolean }

function Dot({ ok }: { ok: boolean }) {
  return <span className={ok ? 'dot dot-ok' : 'dot dot-bad'} aria-hidden="true" />
}

function InstallCard() {
  const [state, setState] = useState(installState)
  if (state.kind === 'installed') return null

  return (
    <section className="card">
      <h2>Install on your phone</h2>
      {state.kind === 'prompt-ready' && (
        <>
          <p>Add this to your home screen and it opens without browser chrome.</p>
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
          Tap <strong>Share</strong>, then <strong>Add to Home Screen</strong>.
        </p>
      )}
      {state.kind === 'ios-other-browser' && (
        <p>
          iOS only allows installing from Safari. Open this page there, then{' '}
          <strong>Share → Add to Home Screen</strong>.
        </p>
      )}
      {state.kind === 'unsupported' && (
        <p className="muted">
          Installing needs Chrome on Android or Safari on iOS. Everything works here
          regardless.
        </p>
      )}
    </section>
  )
}

export default function Home() {
  const { athlete } = useAuth()
  const { data } = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/health/'),
    refetchInterval: 30_000,
    retry: false,
  })

  return (
    <main className="page">
      <header className="header">
        <h1>
          Hello, {athlete?.display_name}
          <span className="mark">.</span>
        </h1>
        <p className="muted">
          {athlete?.training_days_per_week} training days a week · {athlete?.timezone}
        </p>
      </header>

      <GarminCard />

      <InstallCard />

      <section className="card">
        <h2>System</h2>
        <ul className="checks">
          <li>
            <Dot ok={Boolean(data?.db)} /> Database
          </li>
          <li>
            <Dot ok={Boolean(data?.redis)} /> Queue
          </li>
        </ul>
      </section>
    </main>
  )
}
