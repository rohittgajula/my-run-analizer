import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { AuthProvider, useAuth } from './lib/AuthContext'
import { Shell } from './components/Shell'
import Activities from './pages/Activities'
import Calendar from './pages/Calendar'
import Chat from './pages/Chat'
import ActivityDetail from './pages/ActivityDetail'
import Health from './pages/Health'
import Home from './pages/Home'
import Login from './pages/Login'
import Onboarding from './pages/Onboarding'
import Plan from './pages/Plan'
import Register from './pages/Register'
import Settings from './pages/Settings'

function RequireAuth({ children, bare }: { children: ReactNode; bare?: boolean }) {
  const { athlete, loading } = useAuth()
  const location = useLocation()

  // Without this the app flashes the login screen on every reload while the refresh
  // cookie is still being exchanged for an access token.
  if (loading) return <div className="booting" />
  if (!athlete) return <Navigate to="/login" replace state={{ from: location }} />

  // Onboarding is decided by a flag on the athlete, never by navigating after
  // registration: adopting the session re-renders the guards, and the redirect to
  // "/" won that race every time, skipping onboarding silently.
  if (!athlete.onboarding_complete && location.pathname !== '/onboarding') {
    return <Navigate to="/onboarding" replace />
  }
  return bare ? <>{children}</> : <Shell>{children}</Shell>
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { athlete, loading } = useAuth()
  if (loading) return <div className="booting" />
  if (!athlete) return <>{children}</>
  return <Navigate to={athlete.onboarding_complete ? '/' : '/onboarding'} replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
          <Route path="/register" element={<GuestOnly><Register /></GuestOnly>} />
          {/* Onboarding renders without the shell: there is nowhere else to go yet. */}
          <Route path="/onboarding" element={<RequireAuth bare><Onboarding /></RequireAuth>} />
          <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />
          <Route path="/coach" element={<RequireAuth><Chat /></RequireAuth>} />
          <Route path="/activities" element={<RequireAuth><Activities /></RequireAuth>} />
          <Route path="/activities/:id" element={<RequireAuth><ActivityDetail /></RequireAuth>} />
          <Route path="/calendar" element={<RequireAuth><Calendar /></RequireAuth>} />
          <Route path="/health" element={<RequireAuth><Health /></RequireAuth>} />
          <Route path="/plan" element={<RequireAuth><Plan /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
