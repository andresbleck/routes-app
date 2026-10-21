import { AlertCircleIcon, Loader2Icon, TruckIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { checkHealth } from '@/api/client'
import { RecommendationBanner } from '@/components/RecommendationBanner'
import { RouteCard } from '@/components/RouteCard'
import { TripForm } from '@/components/TripForm'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { usePlanTrip } from '@/hooks/usePlanTrip'
import { cn } from '@/lib/utils'
import { TripMap } from '@/map/TripMap'

export default function App() {
  const { result, loading, error, submit } = usePlanTrip()
  // null means "the recommended route" for the current plan.
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null)
  const [shownPlan, setShownPlan] = useState(result?.plan)

  // A new plan starts on its recommended route.
  if (result?.plan !== shownPlan) {
    setShownPlan(result?.plan)
    setSelectedRouteId(null)
  }

  // Wakes up the backend (Render's free tier sleeps) before the first search.
  useEffect(() => {
    checkHealth().catch(() => undefined)
  }, [])

  const activeRouteId = result ? (selectedRouteId ?? result.plan.recommendation.route_id) : null

  return (
    <div className="flex h-dvh flex-col md:flex-row">
      <aside className="flex max-h-[50dvh] w-full shrink-0 flex-col gap-5 overflow-y-auto border-b bg-background p-4 md:max-h-none md:w-96 md:border-r md:border-b-0">
        <header className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <TruckIcon className="size-5" />
          </div>
          <div>
            <h1 className="font-heading text-base leading-tight font-semibold">Weather-Aware Truck Routing</h1>
            <p className="text-xs text-muted-foreground">Safest route by weather, load and time</p>
          </div>
        </header>

        <TripForm loading={loading} onSubmit={submit} />

        <div aria-live="polite" className="flex flex-col gap-3">
          {error && (
            <Alert variant="destructive">
              <AlertCircleIcon />
              <AlertTitle>Could not plan this trip</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {result && (
            <section
              aria-label="Route options"
              aria-busy={loading}
              className={cn('flex flex-col gap-3 transition-opacity', loading && 'pointer-events-none opacity-50')}
            >
              <RecommendationBanner plan={result.plan} />
              {result.plan.routes.map((route) => (
                <RouteCard
                  key={route.id}
                  route={route}
                  selected={route.id === activeRouteId}
                  onSelect={() => setSelectedRouteId(route.id)}
                />
              ))}
            </section>
          )}
        </div>
      </aside>

      <main className="relative min-h-0 flex-1">
        <TripMap
          plan={result?.plan ?? null}
          trip={result?.trip ?? null}
          selectedRouteId={activeRouteId}
          onSelectRoute={setSelectedRouteId}
        />
        <MapStatus loading={loading} empty={!result} />
      </main>
    </div>
  )
}

/** A small pill over the map: what to do first, or that new routes are loading. */
function MapStatus({ loading, empty }: { loading: boolean; empty: boolean }) {
  if (!loading && !empty) return null
  return (
    // Below the risk legend (shown from the sm breakpoint) once a plan is on the map.
    <div
      className={cn(
        'pointer-events-none absolute inset-x-0 z-[1000] flex justify-center px-16',
        empty ? 'top-3' : 'top-3 sm:top-16',
      )}
    >
      <div className="flex items-center gap-2 rounded-full bg-background/95 px-4 py-2 text-sm shadow-md ring-1 ring-foreground/10">
        {loading ? (
          <>
            <Loader2Icon className="size-4 animate-spin" />
            {empty ? 'Checking routes and weather…' : 'Updating routes…'}
          </>
        ) : (
          'Enter an origin and destination to compare 3 truck routes.'
        )}
      </div>
    </div>
  )
}
