"""Plan a trip: routes -> checkpoints -> weather at ETA -> risk -> ranking,
plus a 0–48 h weather heatmap over the trip corridor.

Returns the JSON-ready response described in the README's API contract.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from trips.clients import open_meteo
from trips.clients.open_meteo import HourlyForecast, WeatherSample
from trips.clients.tomtom import TruckRoute
from trips.domain.heatmap_grid import HeatmapGrid, corridor_grid
from trips.domain.ranking import RouteSummary, explain, rank_routes, summarize_route
from trips.domain.risk import RiskAssessment, RiskLevel, classify_checkpoint, severity_score
from trips.domain.route_geometry import simplify_polyline
from trips.domain.sampling import Checkpoint, LatLon, cumulative_miles, resolve_interval, sample_checkpoints
from trips.services.route_options import get_route_options

# Routing uses the truck's gross weight; the risk rules use the load weight.
TARE_WEIGHT_LB = 35_000
KG_PER_LB = 0.45359237
GEOMETRY_TOLERANCE_DEGREES = 0.0005  # ~50 m, keeps the payload small
COORDINATE_DECIMALS = 5
HEATMAP_HOURS = 48


@dataclass(frozen=True)
class AssessedCheckpoint:
    checkpoint: Checkpoint
    segment_miles: float  # scaled so a route's segments add up to its distance
    weather: WeatherSample
    risk: RiskAssessment


@dataclass(frozen=True)
class AssessedRoute:
    route_id: str
    route: TruckRoute
    checkpoints: list[AssessedCheckpoint]
    summary: RouteSummary


def plan_trip(
    origin: LatLon,
    destination: LatLon,
    departure: datetime,
    load_weight_lb: float,
    requested_interval: int | None,
) -> dict:
    routes, warnings = get_route_options(origin, destination, departure, vehicle_weight_kg(load_weight_lb))

    interval = resolve_interval(requested_interval, max(route.distance_miles for route in routes))
    if requested_interval and interval != requested_interval:
        warnings.append(f"Sampling every {interval} mi instead of {requested_interval} mi to limit checkpoints.")

    checkpoints = [sample_checkpoints(r.points, r.cumulative_seconds, interval, departure) for r in routes]
    grid = corridor_grid([route.points for route in routes])
    heatmap_start = departure.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    weather, grid_forecasts = _fetch_weather(checkpoints, grid, heatmap_start)
    assessed = [
        _assess_route(f"route-{i + 1}", route, route_checkpoints, route_weather, load_weight_lb)
        for i, (route, route_checkpoints, route_weather) in enumerate(zip(routes, checkpoints, weather))
    ]

    ranking = rank_routes([route.summary for route in assessed])
    if all(summary.has_no_travel for summary in ranking.routes):
        warnings.append("Every route crosses No Travel conditions; consider delaying the departure.")

    by_id = {route.route_id: route for route in assessed}
    return {
        "interval_miles": interval,
        "departure_time": _iso(departure),
        "load_weight_lb": load_weight_lb,
        "recommendation": {
            "route_id": ranking.recommended.route_id,
            "decided_by": ranking.decided_by.name if ranking.decided_by else None,
            "explanation": explain(ranking),
        },
        "routes": [
            _route_payload(by_id[summary.route_id], rank) for rank, summary in enumerate(ranking.routes, start=1)
        ],
        "heatmap": _heatmap_payload(grid, grid_forecasts, heatmap_start, load_weight_lb),
        "warnings": warnings,
    }


def vehicle_weight_kg(load_weight_lb: float) -> int:
    return round((TARE_WEIGHT_LB + load_weight_lb) * KG_PER_LB)


def _fetch_weather(
    checkpoints: list[list[Checkpoint]], grid: HeatmapGrid, heatmap_start: datetime
) -> tuple[list[list[WeatherSample]], list[HourlyForecast]]:
    """One batched lookup for every checkpoint and heatmap point. Returns the
    weather at each checkpoint's ETA (per route) and the grid forecasts."""
    flat = [checkpoint for route in checkpoints for checkpoint in route]
    end = max(max(c.eta for c in flat), heatmap_start + timedelta(hours=HEATMAP_HOURS))
    forecasts = open_meteo.hourly_forecasts([(c.lat, c.lon) for c in flat] + grid.points, heatmap_start, end)

    checkpoint_forecasts = iter(forecasts[: len(flat)])
    weather = [[next(checkpoint_forecasts).at(checkpoint.eta) for checkpoint in route] for route in checkpoints]
    return weather, forecasts[len(flat) :]


def _heatmap_payload(
    grid: HeatmapGrid, forecasts: list[HourlyForecast], start: datetime, load_weight_lb: float
) -> dict:
    """Severity (0–1) of every grid point for each hour from departure to +48 h."""
    frames = []
    for hour in range(HEATMAP_HOURS + 1):
        moment = start + timedelta(hours=hour)
        samples = [forecast.at(moment) for forecast in forecasts]
        frames.append(
            [
                round(severity_score(s.gust_mph, s.rain_in_hr, s.snow_in_hr, load_weight_lb) / RiskLevel.NO_TRAVEL, 2)
                for s in samples
            ]
        )
    return {
        "start_time": _iso(start),
        "step_minutes": 60,
        "frame_count": len(frames),
        "grid_step_degrees": grid.step_degrees,
        "points": [[lat, lon] for lat, lon in grid.points],
        "frames": frames,
    }


def _assess_route(
    route_id: str,
    route: TruckRoute,
    checkpoints: list[Checkpoint],
    weather: list[WeatherSample],
    load_weight_lb: float,
) -> AssessedRoute:
    # Sampled miles follow the polyline; scale them to the provider's distance.
    scale = route.distance_miles / cumulative_miles(route.points)[-1]
    assessed = [
        AssessedCheckpoint(
            checkpoint=checkpoint,
            segment_miles=checkpoint.segment_miles * scale,
            weather=sample,
            risk=classify_checkpoint(sample.gust_mph, sample.rain_in_hr, sample.snow_in_hr, load_weight_lb),
        )
        for checkpoint, sample in zip(checkpoints, weather)
    ]
    summary = summarize_route(route_id, route.duration_seconds, [(c.segment_miles, c.risk.level) for c in assessed])
    return AssessedRoute(route_id, route, assessed, summary)


def _route_payload(assessed: AssessedRoute, rank: int) -> dict:
    route, summary = assessed.route, assessed.summary
    arrival = assessed.checkpoints[-1].checkpoint.eta
    return {
        "id": assessed.route_id,
        "rank": rank,
        "is_recommended": rank == 1,
        "distance_miles": round(route.distance_miles, 1),
        "duration_minutes": round(route.duration_seconds / 60),
        "arrival_time": _iso(arrival),
        "geometry": [
            [round(lat, COORDINATE_DECIMALS), round(lon, COORDINATE_DECIMALS)]
            for lat, lon in simplify_polyline(route.points, GEOMETRY_TOLERANCE_DEGREES)
        ],
        "risk_summary": {
            "miles_by_level": {level.label: round(miles, 1) for level, miles in summary.miles_by_level.items()},
            "average_risk": round(summary.average_risk, 2),
            "max_level": summary.max_level.label,
            "has_no_travel": summary.has_no_travel,
        },
        "checkpoints": [_checkpoint_payload(checkpoint) for checkpoint in assessed.checkpoints],
    }


def _checkpoint_payload(assessed: AssessedCheckpoint) -> dict:
    checkpoint, weather, risk = assessed.checkpoint, assessed.weather, assessed.risk
    return {
        "index": checkpoint.index,
        "lat": round(checkpoint.lat, COORDINATE_DECIMALS),
        "lon": round(checkpoint.lon, COORDINATE_DECIMALS),
        "distance_miles": round(checkpoint.distance_miles, 1),
        "segment_miles": round(assessed.segment_miles, 1),
        "eta": _iso(checkpoint.eta),
        "weather": {
            "forecast_time": _iso(weather.time),
            "wind_mph": round(weather.wind_mph, 1),
            "gust_mph": round(weather.gust_mph, 1),
            "rain_in_hr": round(weather.rain_in_hr, 3),
            "snow_in_hr": round(weather.snow_in_hr, 3),
        },
        "risk": {
            "level": risk.level.label,
            "score": int(risk.level),
            "drivers": list(risk.drivers),
            "load_adjusted": risk.load_adjusted,
        },
    }


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

