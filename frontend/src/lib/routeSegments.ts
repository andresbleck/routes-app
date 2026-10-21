import type { Route, RiskLevel } from '@/api/types'

export interface RiskSegment {
  level: RiskLevel
  positions: Array<[number, number]>
}

/**
 * Splits a route's geometry into runs of the same risk level. Each checkpoint
 * covers the stretch halfway to its neighbours (as in the backend), matched
 * by the fraction of the route travelled, so the simplified geometry and the
 * checkpoint mileage line up.
 */
export function riskSegments(route: Route): RiskSegment[] {
  const { geometry, checkpoints } = route
  const totalCheckpointMiles = checkpoints[checkpoints.length - 1].distance_miles
  // Fraction of the route where each checkpoint's stretch ends.
  const ends = checkpoints.map((checkpoint, i) => {
    const next = checkpoints[i + 1]
    return next ? (checkpoint.distance_miles + next.distance_miles) / 2 / totalCheckpointMiles : 1
  })

  const travelled = cumulativeDistances(geometry)
  const total = travelled[travelled.length - 1] || 1

  const segments: RiskSegment[] = []
  let checkpointIndex = 0
  geometry.forEach((position, i) => {
    while (checkpointIndex < ends.length - 1 && travelled[i] / total > ends[checkpointIndex]) checkpointIndex++
    const level = checkpoints[checkpointIndex].risk.level
    const current = segments[segments.length - 1]
    if (current?.level === level) {
      current.positions.push(position)
    } else {
      // Start the new run at the previous point so runs connect without gaps.
      const previous = geometry[i - 1]
      segments.push({ level, positions: previous ? [previous, position] : [position] })
    }
  })
  return segments
}

function cumulativeDistances(points: Array<[number, number]>): number[] {
  const distances = [0]
  for (let i = 1; i < points.length; i++) {
    distances.push(distances[i - 1] + approximateDistance(points[i - 1], points[i]))
  }
  return distances
}

/** Equirectangular distance in degrees; only ratios are used, so units don't matter. */
function approximateDistance([lat1, lon1]: [number, number], [lat2, lon2]: [number, number]): number {
  const x = (lon2 - lon1) * Math.cos((((lat1 + lat2) / 2) * Math.PI) / 180)
  const y = lat2 - lat1
  return Math.sqrt(x * x + y * y)
}
