"""Checkpoint sampling along a route polyline.

A route is a list of (lat, lon) vertices plus the cumulative driving time at
each vertex (from the routing provider). Checkpoints are placed every
`interval_miles` from the origin, plus one at the destination; each gets the
truck's ETA by interpolating the cumulative time at its position.
"""

import bisect
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

EARTH_RADIUS_MILES = 3958.8

AUTO_INTERVALS = ((150, 10), (600, 25))  # (max route miles, interval)
LONG_ROUTE_INTERVAL = 50
INTERVAL_OPTIONS = (10, 25, 50)
MAX_CHECKPOINTS_PER_ROUTE = 80

LatLon = tuple[float, float]


@dataclass(frozen=True)
class Checkpoint:
    index: int
    lat: float
    lon: float
    distance_miles: float  # from the origin along the route
    segment_miles: float  # stretch of road this checkpoint represents
    eta: datetime


def haversine_miles(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def cumulative_miles(points: list[LatLon]) -> list[float]:
    totals = [0.0]
    for a, b in zip(points, points[1:]):
        totals.append(totals[-1] + haversine_miles(a, b))
    return totals


def proportional_seconds(miles: list[float], total_seconds: float) -> list[float]:
    """Fallback when the provider gives no per-segment times: constant speed."""
    total_miles = miles[-1]
    if total_miles == 0:
        return [0.0] * len(miles)
    return [total_seconds * m / total_miles for m in miles]


def seconds_from_anchors(miles: list[float], anchors: list[tuple[int, float]]) -> list[float]:
    """Cumulative seconds at every vertex from a few known (vertex_index, seconds)
    anchors, e.g. the provider's turn-by-turn instructions. Between anchors the
    time is spread by distance. Anchors must include the first and last vertex."""
    seconds = []
    for (start_i, start_s), (end_i, end_s) in zip(anchors, anchors[1:]):
        span = miles[end_i] - miles[start_i]
        for vertex in range(start_i, end_i):
            t = 0.0 if span == 0 else (miles[vertex] - miles[start_i]) / span
            seconds.append(_lerp(start_s, end_s, t))
    seconds.append(anchors[-1][1])
    return seconds


def pick_interval(route_miles: float) -> int:
    for max_miles, interval in AUTO_INTERVALS:
        if route_miles <= max_miles:
            return interval
    return LONG_ROUTE_INTERVAL


def resolve_interval(requested: int | None, longest_route_miles: float) -> int:
    """Use the requested interval (or the automatic one), widened if a route
    would exceed MAX_CHECKPOINTS_PER_ROUTE."""
    interval = requested or pick_interval(longest_route_miles)
    for option in INTERVAL_OPTIONS:
        if option >= interval and longest_route_miles / option + 1 <= MAX_CHECKPOINTS_PER_ROUTE:
            return option
    return INTERVAL_OPTIONS[-1]


def sample_checkpoints(
    points: list[LatLon],
    cumulative_seconds: list[float],
    interval_miles: float,
    departure: datetime,
) -> list[Checkpoint]:
    miles = cumulative_miles(points)
    total = miles[-1]

    distances = [i * interval_miles for i in range(int(total // interval_miles) + 1)]
    if total - distances[-1] > 1e-6:
        distances.append(total)

    checkpoints = []
    for index, distance in enumerate(distances):
        i, t = _locate(miles, distance)
        (lat_a, lon_a), (lat_b, lon_b) = points[i - 1], points[i]
        seconds = _lerp(cumulative_seconds[i - 1], cumulative_seconds[i], t)
        checkpoints.append(
            Checkpoint(
                index=index,
                lat=_lerp(lat_a, lat_b, t),
                lon=_lerp(lon_a, lon_b, t),
                distance_miles=distance,
                segment_miles=_segment_miles(distances, index, total),
                eta=departure + timedelta(seconds=seconds),
            )
        )
    return checkpoints


def _locate(miles: list[float], distance: float) -> tuple[int, float]:
    """Return (i, t) so the position lies at fraction t between vertices i-1 and i."""
    i = min(max(bisect.bisect_right(miles, distance), 1), len(miles) - 1)
    start, end = miles[i - 1], miles[i]
    t = 0.0 if end == start else (distance - start) / (end - start)
    return i, t


def _segment_miles(distances: list[float], index: int, total: float) -> float:
    """Each checkpoint covers half the gap to its neighbours, so all segments
    add up to the route length."""
    start = 0.0 if index == 0 else (distances[index - 1] + distances[index]) / 2
    end = total if index == len(distances) - 1 else (distances[index] + distances[index + 1]) / 2
    return end - start


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t
