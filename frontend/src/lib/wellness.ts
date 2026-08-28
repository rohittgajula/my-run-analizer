import type { Activity, DailyMetrics } from './auth'

/** Mean of the values that exist. Null when there are none — never 0. */
export const mean = (values: Array<number | null | undefined>): number | null => {
  const present = values.filter((v): v is number => typeof v === 'number')
  return present.length ? present.reduce((a, b) => a + b, 0) / present.length : null
}

export const latest = <K extends keyof DailyMetrics>(
  days: DailyMetrics[],
  key: K,
): DailyMetrics[K] | null => days.find((d) => d[key] != null)?.[key] ?? null

/** Newest-first from the API; charts read left-to-right. */
export const chronological = (days: DailyMetrics[]) => [...days].reverse()

export const toSeries = (days: DailyMetrics[], key: keyof DailyMetrics) =>
  chronological(days).map((d) => ({ date: d.metric_date, value: d[key] as number | null }))

/**
 * How a value compares with its own recent baseline.
 *
 * Deliberately relative: an HRV of 47 ms means nothing in the abstract and a great
 * deal against your own 28-day average. Returns null rather than guessing when the
 * baseline is too thin to compare against.
 */
export function versusBaseline(
  current: number | null,
  history: Array<number | null>,
  minObservations = 7,
): { delta: number; percent: number } | null {
  const baseline = mean(history)
  const present = history.filter((v): v is number => typeof v === 'number')
  if (current == null || baseline == null || present.length < minObservations) return null
  return { delta: current - baseline, percent: ((current - baseline) / baseline) * 100 }
}

export const sleepHours = (seconds: number | null | undefined) =>
  seconds == null ? null : seconds / 3600

/** Weekly running distance from segmented metrics — running only, never the logged total. */
export function weeklyRunDistance(activities: Activity[]): Array<{ date: string; value: number }> {
  const byWeek = new Map<string, number>()
  for (const activity of activities) {
    const metrics = activity.metrics
    if (!metrics || metrics.run_block_count === 0) continue
    const date = new Date(`${activity.local_date}T00:00:00`)
    // Week starting Monday.
    const monday = new Date(date)
    monday.setDate(date.getDate() - ((date.getDay() + 6) % 7))
    const key = monday.toISOString().slice(0, 10)
    byWeek.set(key, (byWeek.get(key) ?? 0) + metrics.run_distance_m)
  }
  return [...byWeek.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, value]) => ({ date, value: Math.round(value) }))
}

export const READINESS_TONE = (score: number | null) =>
  score == null ? '#5a5a66' : score >= 75 ? '#3ddc97' : score >= 40 ? '#ffb800' : '#ff4d6d'

export const SLEEP_TONE = (score: number | null) =>
  score == null ? '#5a5a66' : score >= 75 ? '#3ddc97' : score >= 50 ? '#ffb800' : '#ff4d6d'
