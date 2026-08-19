const BASE = import.meta.env.VITE_API_BASE ?? '/api'

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

export async function api<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { credentials: 'include' })
  if (!response.ok) {
    // A failing health check answers 503 with a body naming the dependency that
    // broke. Reading it is the whole point of the endpoint, so parse before throwing.
    const detail = await response.json().catch(() => null)
    throw new ApiError(response.status, detail ? JSON.stringify(detail) : response.statusText)
  }
  return response.json() as Promise<T>
}

export type Health = {
  status: 'ok' | 'degraded'
  db: boolean
  redis: boolean
  errors?: Record<string, string>
}
