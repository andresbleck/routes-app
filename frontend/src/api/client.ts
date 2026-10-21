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

/**
 * Plans a trip in three steps. The backend computes routes and checkpoints and
 * returns Open-Meteo URLs; the browser fetches the weather (Open-Meteo limits
 * its free tier per IP, and cloud servers' shared IPs are often over it); the
 * backend then computes risk, ranking and the heatmap from that weather.
 */
export async function planTrip(trip: TripPlanRequest, signal?: AbortSignal): Promise<TripPlan> {
  const pending = await request<{ plan_id: string; weather_urls: string[] }>('/api/trips/plan', {
    method: 'POST',
    body: JSON.stringify(trip),
    signal,
  })
  const locations = await fetchWeather(pending.weather_urls, signal)
  return request(`/api/trips/plan/${pending.plan_id}/weather`, {
    method: 'POST',
    body: JSON.stringify({ locations }),
    signal,
  })
}

/** Fetches the Open-Meteo URLs in parallel; returns one location per point, in order. */
async function fetchWeather(urls: string[], signal?: AbortSignal): Promise<Array<{ hourly: unknown }>> {
  const batches = await Promise.all(
    urls.map(async (url) => {
      let response: Response
      try {
        response = await fetch(url, { signal })
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') throw error
        throw new ApiError(0, 'Cannot reach the weather service (Open-Meteo). Check your connection and try again.')
      }
      if (!response.ok) {
        throw new ApiError(
          response.status,
          response.status === 429
            ? 'The weather service is limiting requests from this network. Please try again in a minute.'
            : 'The weather service is unavailable. Please try again in a moment.',
        )
      }
      const body: unknown = await response.json()
      // A single location comes back as an object, several as an array.
      return Array.isArray(body) ? body : [body]
    }),
  )
  // Send only the hourly data the backend needs.
  return batches.flat().map((location) => ({ hourly: (location as { hourly: unknown }).hourly }))
}
