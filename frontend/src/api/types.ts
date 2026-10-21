// Mirrors the backend API contract (see README).

export type RiskLevel = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'

export type IntervalOption = 'auto' | 10 | 25 | 50

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface TripPlanRequest {
  origin: Place
  destination: Place
  departure_time: string // ISO 8601
  load_weight_lb: number
  interval_miles: IntervalOption
}

export interface Checkpoint {
  index: number
  lat: number
  lon: number
  distance_miles: number
  segment_miles: number
  eta: string
  weather: {
    forecast_time: string
    wind_mph: number
    gust_mph: number
    rain_in_hr: number
    snow_in_hr: number
  }
  risk: {
    level: RiskLevel
    score: number
    drivers: Array<'wind' | 'rain' | 'snow'>
    load_adjusted: boolean
  }
}

export interface Route {
  id: string
  rank: number
  is_recommended: boolean
  distance_miles: number
  duration_minutes: number
  arrival_time: string
  geometry: Array<[number, number]>
  risk_summary: {
    miles_by_level: Record<RiskLevel, number>
    average_risk: number
    max_level: RiskLevel
    has_no_travel: boolean
  }
  checkpoints: Checkpoint[]
}

export interface Heatmap {
  start_time: string
  step_minutes: number
  frame_count: number
  grid_step_degrees: number
  points: Array<[number, number]>
  frames: number[][] // frames[hour][point], 0–1
}

export interface TripPlan {
  interval_miles: number
  departure_time: string
  load_weight_lb: number
  recommendation: {
    route_id: string
    decided_by: string | null
    explanation: string
  }
  routes: Route[]
  heatmap: Heatmap
  warnings: string[]
}
