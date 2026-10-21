"""Grid of weather sample points covering the trip corridor.

The corridor is every route buffered by CORRIDOR_BUFFER_MILES. Points sit on
a global lattice (multiples of the step in degrees), so similar trips reuse
the same points and their cached forecasts. The finest step that keeps the
grid within MAX_GRID_POINTS is used, since every point costs one weather
API call on Open-Meteo's free tier.
"""

import math
from dataclasses import dataclass

from shapely.geometry import Point
from shapely.ops import unary_union
from shapely.prepared import prep

from trips.domain.route_geometry import MILES_PER_DEGREE_LAT, lon_scale, project, projected_line
from trips.domain.sampling import LatLon

CORRIDOR_BUFFER_MILES = 30
GRID_STEPS_DEGREES = (0.1, 0.2, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
MAX_GRID_POINTS = 150


@dataclass(frozen=True)
class HeatmapGrid:
    step_degrees: float
    points: list[LatLon]


def corridor_grid(routes: list[list[LatLon]]) -> HeatmapGrid:
    all_points = [point for route in routes for point in route]
    scale = lon_scale(min(all_points), max(all_points))
    corridor = unary_union([projected_line(route, scale) for route in routes]).buffer(
        CORRIDOR_BUFFER_MILES / MILES_PER_DEGREE_LAT
    )
    contains = prep(corridor).contains
    min_x, min_y, max_x, max_y = corridor.bounds

    for step in GRID_STEPS_DEGREES:
        points = [
            (lat, lon)
            for lat in _lattice(min_y, max_y, step)
            for lon in _lattice(min_x / scale, max_x / scale, step)
            if contains(Point(project((lat, lon), scale)))
        ]
        if len(points) <= MAX_GRID_POINTS:
            break
    return HeatmapGrid(step, points)


def _lattice(start: float, end: float, step: float) -> list[float]:
    """Multiples of `step` within [start, end]."""
    first, last = math.ceil(start / step), math.floor(end / step)
    return [round(i * step, 4) for i in range(first, last + 1)]
