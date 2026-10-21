import type { Place, TripPlan, TripPlanRequest } from '@/api/types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'Cannot reach the server. Check your connection and try again.')
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(body))
  }
  return body as T
}

/** Turns DRF validation errors ({field: [msg]}) or {detail} into one readable line. */
function errorMessage(body: unknown): string {
  if (body && typeof body === 'object') {
    if ('detail' in body && typeof body.detail === 'string') return body.detail
    const messages = Object.entries(body).flatMap(([field, value]) =>
      (Array.isArray(value) ? value : [value]).map((message) =>
        field === 'non_field_errors' ? String(message) : `${field.replaceAll('_', ' ')}: ${message}`,
      ),
    )
    if (messages.length) return messages.join(' ')
  }
  return 'Something went wrong. Please try again.'
}

export function checkHealth(): Promise<{ status: string }> {
  return request('/api/health')
}

export async function searchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  const { results } = await request<{ results: Place[] }>(`/api/geocode?q=${encodeURIComponent(query)}`, { signal })
  return results
}

export function planTrip(trip: TripPlanRequest, signal?: AbortSignal): Promise<TripPlan> {
  return request('/api/trips/plan', { method: 'POST', body: JSON.stringify(trip), signal })
}
