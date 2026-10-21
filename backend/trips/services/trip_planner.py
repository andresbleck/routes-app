"""Plan a trip in two steps around the weather lookup.

1. `prepare_plan`: routes -> checkpoints with ETAs -> heatmap grid, plus the
   Open-Meteo URLs the browser must fetch (see clients/open_meteo.py).
2. `finish_plan`: with those forecasts, weather at each ETA -> risk -> ranking,
   and the 0–48 h heatmap. Returns the JSON response described in the README.
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
class PendingPlan:
    """Everything computed before the weather is known."""

    departure: datetime
    load_weight_lb: float
    interval: int
    routes: list[TruckRoute]
    checkpoints: list[list[Checkpoint]]  # per route
    grid: HeatmapGrid
    warnings: list[str]
    weather_points: list[LatLon]  # unique (rounded) checkpoint and grid locations

    @property
    def heatmap_start(self) -> datetime:
        return self.departure.astimezone(UTC).replace(minute=0, second=0, microsecond=0)

    @property
    def weather_end(self) -> datetime:
        last_eta = max(checkpoint.eta for route in self.checkpoints for checkpoint in route)
        return max(last_eta, self.heatmap_start + timedelta(hours=HEATMAP_HOURS))

    @property
    def weather_urls(self) -> list[str]:
        return open_meteo.forecast_urls(self.weather_points, self.heatmap_start, self.weather_end)


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


def prepare_plan(
    origin: LatLon,
    destination: LatLon,
    departure: datetime,
    load_weight_lb: float,
    requested_interval: int | None,
) -> PendingPlan:
    routes, warnings = get_route_options(origin, destination, departure, vehicle_weight_kg(load_weight_lb))

    interval = resolve_interval(requested_interval, max(route.distance_miles for route in routes))
    if requested_interval and interval != requested_interval:
        warnings.append(f"Sampling every {interval} mi instead of {requested_interval} mi to limit checkpoints.")

    checkpoints = [sample_checkpoints(r.points, r.cumulative_seconds, interval, departure) for r in routes]
    grid = corridor_grid([route.points for route in routes])
    locations = [(c.lat, c.lon) for route in checkpoints for c in route] + grid.points
    return PendingPlan(
        departure=departure,
        load_weight_lb=load_weight_lb,
        interval=interval,
        routes=routes,
        checkpoints=checkpoints,
        grid=grid,
        warnings=warnings,
        weather_points=list(dict.fromkeys(open_meteo.round_point(location) for location in locations)),
    )


def finish_plan(pending: PendingPlan, forecasts: list[HourlyForecast]) -> dict:
    """`forecasts` holds one forecast per `pending.weather_points`, in order."""
    by_point = dict(zip(pending.weather_points, forecasts))

    def forecast_at(lat: float, lon: float) -> HourlyForecast:
        return by_point[open_meteo.round_point((lat, lon))]

    warnings = list(pending.warnings)
    forecast_end = min(forecast.last_time for forecast in forecasts)
    if pending.weather_end > forecast_end + timedelta(hours=1):
        warnings.append(f"The forecast ends at {_iso(forecast_end)}; later hours reuse the last forecast hour.")

    assessed = [
        _assess_route(
            f"route-{i + 1}",
            route,
            route_checkpoints,
            [forecast_at(c.lat, c.lon).at(c.eta) for c in route_checkpoints],
            pending.load_weight_lb,
        )
        for i, (route, route_checkpoints) in enumerate(zip(pending.routes, pending.checkpoints))
    ]

    ranking = rank_routes([route.summary for route in assessed])
    if all(summary.has_no_travel for summary in ranking.routes):
        warnings.append("Every route crosses No Travel conditions; consider delaying the departure.")

    grid_forecasts = [forecast_at(lat, lon) for lat, lon in pending.grid.points]
    by_id = {route.route_id: route for route in assessed}
    return {
        "interval_miles": pending.interval,
        "departure_time": _iso(pending.departure),
        "load_weight_lb": pending.load_weight_lb,
        "recommendation": {
            "route_id": ranking.recommended.route_id,
            "decided_by": ranking.decided_by.name if ranking.decided_by else None,
            "explanation": explain(ranking),
        },
        "routes": [
            _route_payload(by_id[summary.route_id], rank) for rank, summary in enumerate(ranking.routes, start=1)
        ],
        "heatmap": _heatmap_payload(pending.grid, grid_forecasts, pending.heatmap_start, pending.load_weight_lb),
        "warnings": warnings,
    }


def vehicle_weight_kg(load_weight_lb: float) -> int:
    return round((TARE_WEIGHT_LB + load_weight_lb) * KG_PER_LB)


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
