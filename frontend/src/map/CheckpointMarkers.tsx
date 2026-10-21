import { CircleMarker, Popup } from 'react-leaflet'
import type { Checkpoint } from '@/api/types'
import { formatDateTime, formatNumber } from '@/lib/format'
import { DRIVER_LABELS, RISK_COLORS, RISK_LABELS } from '@/lib/risk'

interface CheckpointMarkersProps {
  checkpoints: Checkpoint[]
}

export function CheckpointMarkers({ checkpoints }: CheckpointMarkersProps) {
  return checkpoints.map((checkpoint) => (
    <CircleMarker
      key={checkpoint.index}
      center={[checkpoint.lat, checkpoint.lon]}
      radius={6}
      pathOptions={{ color: '#ffffff', weight: 2, fillColor: RISK_COLORS[checkpoint.risk.level], fillOpacity: 1 }}
    >
      {/* Explicit pane: otherwise the popup inherits the markers pane and sits under other markers. */}
      <Popup pane="popupPane">
        <CheckpointDetails checkpoint={checkpoint} />
      </Popup>
    </CircleMarker>
  ))
}

function CheckpointDetails({ checkpoint }: { checkpoint: Checkpoint }) {
  const { weather, risk } = checkpoint
  return (
    <div className="flex min-w-48 flex-col gap-2 font-sans text-xs">
      <div className="flex items-center justify-between gap-3">
        <span className="font-semibold">Mile {formatNumber(checkpoint.distance_miles)}</span>
        <span
          className="rounded px-1.5 py-0.5 font-medium text-white"
          style={{ backgroundColor: RISK_COLORS[risk.level] }}
        >
          {RISK_LABELS[risk.level]}
        </span>
      </div>
      <div className="text-muted-foreground">ETA {formatDateTime(checkpoint.eta)}</div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
        <dt className="text-muted-foreground">Wind gusts</dt>
        <dd>
          {formatNumber(weather.gust_mph)} mph <span className="text-muted-foreground">(sustained {formatNumber(weather.wind_mph)})</span>
        </dd>
        <dt className="text-muted-foreground">Rain</dt>
        <dd>{formatNumber(weather.rain_in_hr, 2)} in/hr</dd>
        <dt className="text-muted-foreground">Snow</dt>
        <dd>{formatNumber(weather.snow_in_hr, 2)} in/hr</dd>
      </dl>
      {risk.drivers.length > 0 && (
        <p>
          Driven by {risk.drivers.map((driver) => DRIVER_LABELS[driver]).join(' and ')}
          {risk.load_adjusted && ', raised by the load weight'}.
        </p>
      )}
      <p className="text-[10px] text-muted-foreground">Forecast for {formatDateTime(weather.forecast_time)}</p>
    </div>
  )
}
