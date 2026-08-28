/** Seconds per km as "m:ss". Nobody thinks in 495. */
export const pace = (secondsPerKm: number | null | undefined): string => {
  if (!secondsPerKm || !Number.isFinite(secondsPerKm)) return '—'
  const total = Math.round(secondsPerKm)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

/** Duration as "12:34" or "1:02:33". */
export const duration = (seconds: number | null | undefined): string => {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return h
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`
}

export const km = (metres: number | null | undefined): string =>
  metres == null ? '—' : `${(metres / 1000).toFixed(2)} km`

/** Metres, but as a whole number — for run distances where 967 reads better than 0.97 km. */
export const metres = (value: number | null | undefined): string =>
  value == null ? '—' : `${Math.round(value)} m`

export const day = (iso: string): string =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
