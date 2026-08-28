/**
 * Token handling.
 *
 * The access token lives in this module variable and nowhere else — not
 * localStorage (any injected script could read it and exfiltrate a valid token),
 * not a cookie (that would reintroduce CSRF). It dies on page refresh, which is
 * why `refreshAccess()` runs once on load: the refresh token sits in an httpOnly
 * cookie the browser sends but JavaScript cannot read.
 */

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

let accessToken: string | null = null

/** In-flight refresh, shared so five concurrent 401s cause one refresh, not five. */
let refreshInFlight: Promise<string | null> | null = null

export const setAccessToken = (token: string | null) => {
  accessToken = token
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(typeof detail === 'string' ? detail : 'Request failed')
  }

  /** Flattens DRF's {field: [messages]} into something a form can show. */
  fieldErrors(): Record<string, string> {
    if (!this.detail || typeof this.detail !== 'object') return {}
    return Object.fromEntries(
      Object.entries(this.detail as Record<string, unknown>).map(([key, value]) => [
        key,
        Array.isArray(value) ? String(value[0]) : String(value),
      ]),
    )
  }

  get message(): string {
    const errors = this.fieldErrors()
    return errors.detail ?? Object.values(errors)[0] ?? 'Something went wrong.'
  }
}

async function refreshAccess(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${BASE}/auth/refresh/`, {
      method: 'POST',
      credentials: 'include',
    })
      .then(async (response) => {
        if (!response.ok) return null
        const data = await response.json()
        accessToken = data.access
        return data.access as string
      })
      .catch(() => null)
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const send = () =>
    fetch(`${BASE}${path}`, {
      ...init,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...init.headers,
      },
    })

  let response = await send()

  // A 15-minute access token expires mid-session constantly. Refresh once and
  // replay rather than bouncing the user to login for a token that is merely stale.
  if (response.status === 401 && !path.startsWith('/auth/refresh')) {
    const token = await refreshAccess()
    if (token) response = await send()
  }

  if (!response.ok) {
    const detail = await response.json().catch(() => response.statusText)
    throw new ApiError(response.status, detail)
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) })

/** Called once on load: turns the httpOnly refresh cookie into a live session. */
export async function restoreSession(): Promise<boolean> {
  return (await refreshAccess()) !== null
}

// --- types -------------------------------------------------------------------

export type User = { id: number; username: string; email: string }

export type Athlete = {
  id: number
  display_name: string
  timezone: string
  date_of_birth: string | null
  weight_kg: number | null
  resting_hr: number | null
  max_hr: number | null
  easy_pace_min: number
  easy_pace_max: number
  hr_easy_min: number
  hr_easy_max: number
  hr_ceiling: number
  run_cadence_threshold: number
  available_days: Record<string, boolean>
  long_run_day: number
  training_days_per_week: number
  onboarding_complete: boolean
  garmin_connected: boolean
  garmin_last_sync: string | null
}

export type Session = { user: User; athlete: Athlete; access?: string }
