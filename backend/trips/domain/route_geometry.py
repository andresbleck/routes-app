"""Geometry helpers for building and comparing routes.

Coordinates are projected to a flat plane by scaling longitude with
cos(latitude), which is accurate enough at the scale of a road trip.
In that plane one unit is one degree of latitude (~69 miles).
"""

import math

from shapely.geometry import LineString

from trips.domain.sampling import LatLon

MILES_PER_DEGREE_LAT = 69.0
# Simplifying long polylines (10k+ points) keeps comparisons fast; ~0.1 mi.
SIMPLIFY_TOLERANCE_DEGREES = 0.0015


def detour_point(origin: LatLon, destination: LatLon, offset_fraction: float) -> LatLon:
    """Midpoint between origin and destination, pushed sideways by
    `offset_fraction` of their straight-line distance. Positive values go to
    the left of the direction of travel, negative to the right."""
    scale = lon_scale(origin, destination)
    (ax, ay), (bx, by) = project(origin, scale), project(destination, scale)
    mid_x, mid_y = (ax + bx) / 2, (ay + by) / 2
    # (-dy, dx) is the left-hand perpendicular, as long as the trip itself.
    x = mid_x - (by - ay) * offset_fraction
    y = mid_y + (bx - ax) * offset_fraction
    return (y, x / scale)


def shared_fraction(route: list[LatLon], other: list[LatLon], tolerance_miles: float = 1.0) -> float:
    """Share of `route`'s length that runs within `tolerance_miles` of `other`."""
    scale = lon_scale(route[0], route[-1])
    line = projected_line(route, scale)
    corridor = projected_line(other, scale).buffer(tolerance_miles / MILES_PER_DEGREE_LAT)
    if line.length == 0:
        return 1.0
    return line.intersection(corridor).length / line.length


def simplify_polyline(points: list[LatLon], tolerance_degrees: float) -> list[LatLon]:
    """Fewer points for drawing; the shape stays within `tolerance_degrees`."""
    simplified = LineString(points).simplify(tolerance_degrees, preserve_topology=False)
    return [(lat, lon) for lat, lon in simplified.coords]


def lon_scale(a: LatLon, b: LatLon) -> float:
    return math.cos(math.radians((a[0] + b[0]) / 2))


def project(point: LatLon, scale: float) -> tuple[float, float]:
    lat, lon = point
    return (lon * scale, lat)


def projected_line(points: list[LatLon], scale: float) -> LineString:
    return LineString([project(p, scale) for p in points]).simplify(SIMPLIFY_TOLERANCE_DEGREES)
