import { StarIcon } from 'lucide-react'
import type { Route } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { formatDateTime, formatDuration, formatMiles, formatNumber } from '@/lib/format'
import { RISK_COLORS, RISK_LABELS, RISK_LEVELS } from '@/lib/risk'
import { cn } from '@/lib/utils'

interface RouteCardProps {
  route: Route
  selected: boolean
  onSelect: () => void
}

export function RouteCard({ route, selected, onSelect }: RouteCardProps) {
  const { risk_summary: risk } = route

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'flex w-full flex-col gap-2.5 rounded-xl border bg-card p-3 text-left text-sm transition-colors hover:bg-muted/50',
        selected && 'border-foreground/40 ring-2 ring-foreground/10',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">Route {route.rank}</span>
        <div className="flex items-center gap-1.5">
          {route.is_recommended && (
            <Badge>
              <StarIcon /> Recommended
            </Badge>
          )}
          <Badge variant="outline" className="gap-1.5">
            <span className="size-2 rounded-full" style={{ backgroundColor: RISK_COLORS[risk.max_level] }} />
            Max {RISK_LABELS[risk.max_level]}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Stat label="Distance" value={formatMiles(route.distance_miles)} />
        <Stat label="Drive time" value={formatDuration(route.duration_minutes)} />
        <Stat label="Avg risk" value={`${formatNumber(risk.average_risk, 2)} / 4`} />
      </div>

      <MilesByLevelBar milesByLevel={risk.miles_by_level} total={route.distance_miles} />

      <p className="text-xs text-muted-foreground">Arrives {formatDateTime(route.arrival_time)}</p>
    </button>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  )
}

function MilesByLevelBar({ milesByLevel, total }: { milesByLevel: Route['risk_summary']['miles_by_level']; total: number }) {
  const levels = RISK_LEVELS.filter((level) => milesByLevel[level] > 0)
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex h-2 overflow-hidden rounded-full bg-muted">
        {levels.map((level) => (
          <div
            key={level}
            style={{ width: `${(milesByLevel[level] / total) * 100}%`, backgroundColor: RISK_COLORS[level] }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
        {levels.map((level) => (
          <span key={level} className="tabular-nums">
            {RISK_LABELS[level]} {formatMiles(milesByLevel[level])}
          </span>
        ))}
      </div>
    </div>
  )
}
