import { RISK_COLORS, RISK_LABELS, RISK_LEVELS } from '@/lib/risk'

export function RiskLegend() {
  return (
    <div className="pointer-events-auto flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-background/95 px-3 py-2 text-xs shadow-md ring-1 ring-foreground/10">
      <span className="font-medium">Risk</span>
      {RISK_LEVELS.map((level) => (
        <span key={level} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-full" style={{ backgroundColor: RISK_COLORS[level] }} />
          {RISK_LABELS[level]}
        </span>
      ))}
    </div>
  )
}
