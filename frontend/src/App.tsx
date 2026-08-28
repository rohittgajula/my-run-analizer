import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { AuthProvider, useAuth } from './lib/AuthContext'
import Home from './pages/Home'
import Login from './pages/Login'
import Onboarding from './pages/Onboarding'
import Register from './pages/Register'
import Settings from './pages/Settings'

function RequireAuth({ children }: { children: ReactNode }) {
  const { athlete, loading } = useAuth()
  const location = useLocation()

  // Without this the app flashes the login screen on every reload while the refresh
  // cookie is still being exchanged for an access token.
  if (loading) return <div className="booting" />
  if (!athlete) return <Navigate to="/login" replace state={{ from: location }} />

  // Onboarding is decided by a flag on the athlete, never by navigating after
  // registration: adopting the session re-renders the guards, and the redirect
  // to "/" won that race every time, skipping onboarding silently.
  if (!athlete.onboarding_complete && location.pathname !== '/onboarding') {
    return <Navigate to="/onboarding" replace />
  }
  return <>{children}</>
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { athlete, loading } = useAuth()
  if (loading) return <div className="booting" />
  if (!athlete) return <>{children}</>
  return <Navigate to={athlete.onboarding_complete ? '/' : '/onboarding'} replace />
}

function Nav() {
  const { athlete, logout } = useAuth()
  const location = useLocation()
  if (!athlete || !athlete.onboarding_complete || location.pathname === '/onboarding') {
    return null
  }

  return (
    <nav className="nav">
      <div className="nav-inner">
        <Link to="/" className="nav-brand">
          Run Analize<span className="mark">r</span>
        </Link>
        <div className="nav-links">
          <Link to="/settings">Settings</Link>
          <button className="linkish" onClick={logout}>
            Sign out
          </button>
        </div>
      </div>
    </nav>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Nav />
        <Routes>
          <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
          <Route path="/register" element={<GuestOnly><Register /></GuestOnly>} />
          <Route path="/onboarding" element={<RequireAuth><Onboarding /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
          <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
