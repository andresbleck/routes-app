import { useMemo } from 'react'
import { Polyline, Tooltip } from 'react-leaflet'
import type { Route } from '@/api/types'
import { formatDuration, formatMiles } from '@/lib/format'
import { RISK_COLORS } from '@/lib/risk'
import { riskSegments } from '@/lib/routeSegments'

const ALTERNATIVE_COLOR = '#94a3b8'

interface RouteLayersProps {
  routes: Route[]
  selectedId: string
  onSelect: (routeId: string) => void
}

/** Alternatives in grey (click to select); the selected route colored by risk. */
export function RouteLayers({ routes, selectedId, onSelect }: RouteLayersProps) {
  const selected = routes.find((route) => route.id === selectedId)
  const segments = useMemo(() => (selected ? riskSegments(selected) : []), [selected])

  return (
    <>
      {routes
        .filter((route) => route.id !== selectedId)
        .map((route) => (
          <Polyline
            key={route.id}
            positions={route.geometry}
            pathOptions={{ color: ALTERNATIVE_COLOR, weight: 5, opacity: 0.85 }}
            eventHandlers={{ click: () => onSelect(route.id) }}
          >
            <Tooltip pane="tooltipPane" sticky>
              Route #{route.rank} · {formatMiles(route.distance_miles)} · {formatDuration(route.duration_minutes)}
              <br />
              <span className="text-muted-foreground">Click to view details</span>
            </Tooltip>
          </Polyline>
        ))}

      {selected && (
        <>
          {/* White casing keeps the colored line readable over the heatmap. It
              also absorbs clicks, so clicking the selected route never selects
              an alternative that shares the same road underneath. */}
          <Polyline
            positions={selected.geometry}
            bubblingMouseEvents={false}
            pathOptions={{ color: '#ffffff', weight: 9, opacity: 1 }}
          />
          {segments.map((segment, i) => (
            <Polyline
              key={`${selected.id}-${i}`}
              positions={segment.positions}
              interactive={false}
              pathOptions={{ color: RISK_COLORS[segment.level], weight: 5, opacity: 1 }}
            />
          ))}
        </>
      )}
    </>
  )
}
