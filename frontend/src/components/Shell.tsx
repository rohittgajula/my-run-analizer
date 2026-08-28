import { Link, NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { api } from '../lib/auth'
import { useAuth } from '../lib/AuthContext'

type GarminStatus = { connected: boolean; name: string; last_sync: string | null }

const NAV = [
  { to: '/', label: 'Today', end: true },
  { to: '/activities', label: 'Activities' },
  { to: '/health', label: 'Health' },
  { to: '/plan', label: 'Plan' },
  { to: '/settings', label: 'Settings' },
]

/**
 * Connection state as a single dot.
 *
 * It re-probes rather than trusting the stored flag, because the failure mode is a
 * token that looks present and no longer works — and a green dot that means "we
 * think so" is worse than no dot at all.
 */
function ConnectionDot() {
  const { data, isPending } = useQuery({
    queryKey: ['garmin-status'],
    queryFn: () => api<GarminStatus>('/garmin/status/'),
    refetchInterval: 120_000,
    retry: false,
  })

  const state = isPending ? 'pending' : data?.connected ? 'ok' : 'bad'
  const label = isPending
    ? 'Checking Garmin…'
    : data?.connected
      ? `Garmin connected${data.name ? ` — ${data.name}` : ''}${
          data.last_sync ? `, last sync ${new Date(data.last_sync).toLocaleString()}` : ''
        }`
      : 'Garmin not connected'

  return (
    <Link to="/settings" className="conn" title={label} aria-label={label}>
      <span className={`dot dot-${state}`} />
      <span className="conn-text">Garmin</span>
    </Link>
  )
}

export function Shell({ children }: { children: ReactNode }) {
  const { athlete, logout } = useAuth()

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          Run Analize<span className="mark">r</span>
        </div>
        <nav>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `navitem ${isActive ? 'navitem-on' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button className="linkish sidebar-foot" onClick={logout}>
          Sign out {athlete?.display_name ? `(${athlete.display_name})` : ''}
        </button>
      </aside>

      <div className="main">
        <header className="topbar">
          <ConnectionDot />
        </header>
        {children}
      </div>
    </div>
  )
}
