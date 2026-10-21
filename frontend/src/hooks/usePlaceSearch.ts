import { useEffect, useState } from 'react'
import { searchPlaces } from '@/api/client'
import type { Place } from '@/api/types'

const DEBOUNCE_MS = 300
const MIN_QUERY_LENGTH = 2

/** Debounced place suggestions for a search query. */
export function usePlaceSearch(query: string) {
  const [response, setResponse] = useState<{ query: string; results: Place[] }>({ query: '', results: [] })
  const trimmed = query.trim()
  const tooShort = trimmed.length < MIN_QUERY_LENGTH

  useEffect(() => {
    if (tooShort) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      searchPlaces(trimmed, controller.signal)
        .then((results) => setResponse({ query: trimmed, results }))
        .catch(() => {
          if (!controller.signal.aborted) setResponse({ query: trimmed, results: [] })
        })
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [trimmed, tooShort])

  return {
    results: tooShort ? [] : response.results,
    loading: !tooShort && response.query !== trimmed,
    tooShort,
  }
}
