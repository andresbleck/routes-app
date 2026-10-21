import type { RiskLevel } from '@/api/types'

export const RISK_LEVELS: RiskLevel[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

// Single source of risk colors for the map, cards, legend and heatmap.
export const RISK_COLORS: Record<RiskLevel, string> = {
  low: '#16a34a',
  moderate: '#eab308',
  high: '#f97316',
  severe: '#dc2626',
  no_travel: '#7c3aed',
}

export const RISK_LABELS: Record<RiskLevel, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
}

export const DRIVER_LABELS = { wind: 'wind gusts', rain: 'rain', snow: 'snow' } as const
