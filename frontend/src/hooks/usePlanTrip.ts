import { useCallback, useEffect, useRef, useState } from 'react'
import { planTrip } from '@/api/client'
import type { TripPlan, TripPlanRequest } from '@/api/types'

export interface PlanResult {
  plan: TripPlan
  trip: TripPlanRequest
}

/**
 * Requests trip plans. The last successful result stays available while a new
 * search loads or if it fails, so the map never goes blank. A new request
 * cancels the one in flight.
 */
export function usePlanTrip() {
  const [result, setResult] = useState<PlanResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)

  const submit = useCallback(async (trip: TripPlanRequest) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setLoading(true)
    setError(null)
    try {
      const plan = await planTrip(trip, controller.signal)
      setResult({ plan, trip })
    } catch (caught) {
      if (controller.signal.aborted) return
      setError(caught instanceof Error ? caught.message : 'Something went wrong.')
    }
    setLoading(false)
  }, [])

  useEffect(() => () => controllerRef.current?.abort(), [])

  return { result, loading, error, submit }
}
