import { InfoIcon, OctagonAlertIcon, ShieldCheckIcon } from 'lucide-react'
import type { TripPlan } from '@/api/types'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

export function RecommendationBanner({ plan }: { plan: TripPlan }) {
  const recommended = plan.routes.find((route) => route.id === plan.recommendation.route_id)
  const blocked = recommended?.risk_summary.has_no_travel

  return (
    <div className="flex flex-col gap-2">
      <Alert variant={blocked ? 'destructive' : 'default'}>
        {blocked ? <OctagonAlertIcon /> : <ShieldCheckIcon />}
        <AlertTitle>
          {blocked ? 'No route is safe right now' : `Route ${recommended?.rank} is the recommended route`}
        </AlertTitle>
        <AlertDescription>{plan.recommendation.explanation}</AlertDescription>
      </Alert>
      {plan.warnings.map((warning) => (
        <p key={warning} className="flex gap-1.5 text-xs text-muted-foreground">
          <InfoIcon className="mt-px size-3.5 shrink-0" />
          {warning}
        </p>
      ))}
      <p className="text-xs text-muted-foreground">
        Weather sampled every {plan.interval_miles} mi at the truck's estimated arrival time.
      </p>
    </div>
  )
}
