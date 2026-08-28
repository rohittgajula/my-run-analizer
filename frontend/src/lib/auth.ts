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

/**
 * Rotation blacklists the previous refresh token immediately, so two concurrent
 * refreshes are not merely wasteful — the second presents a token the first just
 * revoked and gets a 401, logging the user out. React StrictMode double-invokes
 * effects in development, so this is the normal case, not an edge one.
 */
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
        // Cleared on the next tick, not synchronously: a caller that started while
        // the request was resolving would otherwise begin a second rotation with a
        // cookie the browser has not yet replaced.
        setTimeout(() => {
          refreshInFlight = null
        }, 0)
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
  zones: {
    resting_hr: number
    max_hr: number
    max_source: string
    zones: Array<{ name: string; label: string; low: number; high: number; purpose: string }>
  } | null
  garmin_connected: boolean
  garmin_last_sync: string | null
}

export type Session = { user: User; athlete: Athlete; access?: string }


export type ActivityMetrics = {
  run_distance_m: number
  walk_distance_m: number
  run_fraction: number
  run_duration_s: number
  walk_duration_s: number
  run_block_count: number
  longest_run_m: number
  longest_run_s: number
  run_pace_s_per_km: number | null
  walk_pace_s_per_km: number | null
  blended_pace_s_per_km: number | null
  avg_run_cadence_spm: number | null
  avg_run_hr: number | null
  hr_drift_percent: number | null
  custom_load: number | null
  time_in_zone: Record<string, number> | null
}

export type Segment = {
  index: number
  kind: 'run' | 'walk' | 'stop'
  start_offset_s: number
  duration_s: number
  distance_m: number
  avg_pace_s_per_km: number | null
  avg_cadence_spm: number | null
  hr_avg: number | null
  hr_max: number | null
  hr_recovery_60s: number | null
  hr_overshoot_bpm: number | null
}

export type Activity = {
  id: number
  local_date: string
  sport: string
  started_at: string
  total_distance_m: number
  total_timer_s: number
  total_elapsed_s: number
  avg_hr: number | null
  max_hr: number | null
  avg_cadence_spm: number | null
  segmentation_version: number | null
  metrics: ActivityMetrics | null
  segments?: Segment[]
}


export type DailyMetrics = {
  metric_date: string
  sleep_seconds: number | null
  sleep_need_seconds: number | null
  sleep_score: number | null
  deep_sleep_seconds: number | null
  rem_sleep_seconds: number | null
  awake_seconds: number | null
  hrv_overnight_avg: number | null
  hrv_status: string
  training_readiness: number | null
  training_readiness_level: string
  training_status: string
  acute_load: number | null
  chronic_load: number | null
  acwr: number | null
  resting_hr: number | null
  steps: number | null
  stress_avg: number | null
  body_battery_high: number | null
  body_battery_low: number | null
  intensity_minutes: number | null
  spo2_avg: number | null
  respiration_avg: number | null
  vo2max: number | null
}
