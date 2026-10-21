import { CloudSunIcon } from 'lucide-react'
import { Slider } from '@/components/ui/slider'
import { formatDateTime } from '@/lib/format'
import { RISK_COLORS, RISK_LABELS, RISK_LEVELS } from '@/lib/risk'

interface ForecastSliderProps {
  startTime: string
  maxHour: number
  hour: number
  onChange: (hour: number) => void
}

export function ForecastSlider({ startTime, maxHour, hour, onChange }: ForecastSliderProps) {
  const moment = new Date(new Date(startTime).getTime() + hour * 60 * 60 * 1000).toISOString()

  return (
    <div className="flex w-full flex-col gap-2.5 rounded-xl bg-background/95 p-3 text-xs shadow-md ring-1 ring-foreground/10">
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-1.5 font-medium">
          <CloudSunIcon className="size-4" /> Weather forecast
        </span>
        <span className="tabular-nums">
          <span className="font-medium">{hour === 0 ? 'Departure' : `+${hour} h`}</span>
          <span className="text-muted-foreground"> · {formatDateTime(moment)}</span>
        </span>
      </div>
      <Slider
        min={0}
        max={maxHour}
        step={1}
        value={[hour]}
        onValueChange={([value]) => onChange(value)}
        aria-label="Forecast hour"
      />
      <div className="flex items-center justify-between gap-2 text-muted-foreground">
        <span>0 h</span>
        <div className="flex items-center gap-1.5">
          <span
            className="h-1.5 w-28 rounded-full"
            style={{ background: `linear-gradient(to right, ${RISK_LEVELS.map((level) => RISK_COLORS[level]).join(', ')})` }}
          />
          <span>
            {RISK_LABELS.low} → {RISK_LABELS.no_travel}
          </span>
        </div>
        <span>{maxHour} h</span>
      </div>
    </div>
  )
}
