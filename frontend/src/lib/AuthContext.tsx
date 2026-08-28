import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from 'react'
import { api, json, restoreSession, setAccessToken, type Athlete, type Session } from './auth'

type AuthValue = {
  athlete: Athlete | null
  username: string | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => Promise<void>
  updateAthlete: (patch: Partial<Athlete>) => Promise<Athlete>
}

export type RegisterInput = {
  username: string
  password: string
  email?: string
  display_name?: string
  timezone?: string
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [athlete, setAthlete] = useState<Athlete | null>(null)
  const [username, setUsername] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const adopt = useCallback((session: Session) => {
    if (session.access) setAccessToken(session.access)
    setAthlete(session.athlete)
    setUsername(session.user.username)
  }, [])

  // The access token does not survive a reload; the refresh cookie does. Trade it
  // for a new one before deciding the user is logged out.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (await restoreSession()) {
        try {
          const session = await api<Session>('/auth/me/')
          if (!cancelled) adopt(session)
        } catch {
          /* refresh worked but /me did not — treat as logged out */
        }
      }
      if (!cancelled) setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [adopt])

  const value = useMemo<AuthValue>(
    () => ({
      athlete,
      username,
      loading,
      async login(user, password) {
        adopt(await api<Session>('/auth/login/', { method: 'POST', ...json({ username: user, password }) }))
      },
      async register(input) {
        adopt(await api<Session>('/auth/register/', { method: 'POST', ...json(input) }))
      },
      async logout() {
        try {
          await api('/auth/logout/', { method: 'POST' })
        } finally {
          // Clear locally even if the request failed — the cookie is gone either way
          // and leaving stale state on screen is worse than a redundant logout.
          setAccessToken(null)
          setAthlete(null)
          setUsername(null)
        }
      },
      async updateAthlete(patch) {
        const updated = await api<Athlete>('/athlete/', { method: 'PATCH', ...json(patch) })
        setAthlete(updated)
        return updated
      },
    }),
    [athlete, username, loading, adopt],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
