from datetime import UTC, datetime, timedelta

import pytest
from django.test import Client

from trips.clients.open_meteo import HourlyForecast, WeatherSample
from trips.clients.tomtom import Place, TruckRoute
from trips.domain.sampling import cumulative_miles, proportional_seconds
from trips.exceptions import NoRouteFound, UpstreamError
from trips.services import trip_planner

URL = "/api/trips/plan"
ORIGIN = {"label": "A", "lat": 0.0, "lon": 0.0}
DESTINATION = {"label": "B", "lat": 0.0, "lon": 1.0}


def make_route(points, hours):
    miles = cumulative_miles(points)
    return TruckRoute(
        points=points,
        cumulative_seconds=proportional_seconds(miles, hours * 3600),
        distance_miles=miles[-1] * 1.002,  # provider distance differs slightly from the polyline
        duration_seconds=hours * 3600,
    )


# ~69 mi straight east, and a slower detour through a snowy area to the north.
DIRECT = make_route([(0.0, 0.0), (0.0, 1.0)], hours=1.0)
NORTHERN = make_route([(0.0, 0.0), (0.3, 0.5), (0.0, 1.0)], hours=1.5)


def fake_weather(points, start, end, gust_mph=10.0):
    """Snow (Severe) north of lat 0.1, calm elsewhere."""
    first_hour = start.replace(minute=0, second=0, microsecond=0)
    hours = int((end - first_hour).total_seconds() // 3600) + 2
    forecasts = []
    for lat, _ in points:
        snow = 2.5 if lat > 0.1 else 0.0
        samples = [
            WeatherSample(first_hour + timedelta(hours=h), wind_mph=5, gust_mph=gust_mph, rain_in_hr=0, snow_in_hr=snow)
            for h in range(hours)
        ]
        forecasts.append(HourlyForecast(samples))
    return forecasts


@pytest.fixture
def providers(monkeypatch):
    def install(routes=(DIRECT, NORTHERN), warnings=(), weather=fake_weather):
        def get_route_options(origin, destination, departure, vehicle_weight_kg):
            if isinstance(routes, Exception):
                raise routes
            return list(routes), list(warnings)

        monkeypatch.setattr(trip_planner, "get_route_options", get_route_options)
        monkeypatch.setattr(trip_planner.open_meteo, "hourly_forecasts", weather)

    install()
    return install


def departure(hours_from_now=1.0):
    return (datetime.now(UTC) + timedelta(hours=hours_from_now)).isoformat()


def post(**overrides):
    body = {
        "origin": ORIGIN,
        "destination": DESTINATION,
        "departure_time": departure(),
        "load_weight_lb": 20_000,
        **overrides,
    }
    return Client().post(URL, body, content_type="application/json")


# --- successful plan --------------------------------------------------------


def test_plan_recommends_the_route_without_severe_miles(providers):
    response = post()

    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"]["route_id"] == "route-1"
    assert body["recommendation"]["decided_by"] == "severe_miles"
    assert body["recommendation"]["explanation"].startswith("Recommended for fewest Severe miles")
    assert [route["id"] for route in body["routes"]] == ["route-1", "route-2"]
    assert [route["rank"] for route in body["routes"]] == [1, 2]
    assert body["routes"][0]["is_recommended"] is True
    assert body["routes"][1]["risk_summary"]["max_level"] == "severe"


def test_route_payload_follows_the_contract(providers):
    route = post().json()["routes"][0]

    assert set(route) == {
        "id", "rank", "is_recommended", "distance_miles", "duration_minutes",
        "arrival_time", "geometry", "risk_summary", "checkpoints",
    }  # fmt: skip
    assert route["duration_minutes"] == 60
    assert route["geometry"][0] == [0.0, 0.0]
    assert set(route["risk_summary"]["miles_by_level"]) == {"low", "moderate", "high", "severe", "no_travel"}
    assert set(post().json()) == {
        "interval_miles", "departure_time", "load_weight_lb", "recommendation", "routes", "heatmap", "warnings",
    }  # fmt: skip

    checkpoint = route["checkpoints"][1]
    assert set(checkpoint) == {"index", "lat", "lon", "distance_miles", "segment_miles", "eta", "weather", "risk"}
    assert set(checkpoint["weather"]) == {"forecast_time", "wind_mph", "gust_mph", "rain_in_hr", "snow_in_hr"}
    assert checkpoint["risk"] == {"level": "low", "score": 0, "drivers": [], "load_adjusted": False}
    assert checkpoint["eta"].endswith("Z")


def test_miles_by_level_add_up_to_route_distance(providers):
    for route in post().json()["routes"]:
        total = sum(route["risk_summary"]["miles_by_level"].values())
        assert total == pytest.approx(route["distance_miles"], abs=0.2)


def test_checkpoint_eta_matches_route_timing(providers):
    route = post().json()["routes"][0]
    first = datetime.fromisoformat(route["checkpoints"][0]["eta"])
    last = datetime.fromisoformat(route["checkpoints"][-1]["eta"])

    assert last - first == timedelta(hours=1)
    assert route["arrival_time"] == route["checkpoints"][-1]["eta"]


def test_automatic_interval_for_short_trip(providers):
    body = post().json()

    assert body["interval_miles"] == 10
    assert len(body["routes"][0]["checkpoints"]) == 8  # 0, 10, ... 60 and the destination


def test_requested_interval_is_used(providers):
    body = post(interval_miles=25).json()

    assert body["interval_miles"] == 25
    assert [c["distance_miles"] for c in body["routes"][0]["checkpoints"]][:3] == [0, 25, 50]


def test_load_rules_are_applied(providers):
    providers(routes=[DIRECT], weather=lambda *args: fake_weather(*args, gust_mph=47))

    light = post(load_weight_lb=30_000).json()["routes"][0]["checkpoints"][0]["risk"]
    heavy = post(load_weight_lb=35_000).json()["routes"][0]["checkpoints"][0]["risk"]

    assert light == {"level": "severe", "score": 3, "drivers": ["wind"], "load_adjusted": False}
    assert heavy == {"level": "no_travel", "score": 4, "drivers": ["wind"], "load_adjusted": True}


def test_provider_warnings_are_returned(providers):
    providers(warnings=["generated one route"])

    assert post().json()["warnings"] == ["generated one route"]


def test_warns_when_every_route_has_no_travel(providers):
    providers(routes=[DIRECT], weather=lambda *args: fake_weather(*args, gust_mph=60))

    assert any("No Travel" in warning for warning in post().json()["warnings"])


def test_heatmap_has_49_hourly_frames_from_departure(providers):
    body = post(departure_time=departure(1.5)).json()
    heatmap = body["heatmap"]

    assert heatmap["frame_count"] == 49
    assert len(heatmap["frames"]) == 49
    assert heatmap["step_minutes"] == 60
    start = datetime.fromisoformat(heatmap["start_time"])
    departure_time = datetime.fromisoformat(body["departure_time"])
    assert start <= departure_time < start + timedelta(hours=1)


def test_heatmap_frames_match_grid_points(providers):
    heatmap = post().json()["heatmap"]

    assert len(heatmap["points"]) > 0
    assert all(len(frame) == len(heatmap["points"]) for frame in heatmap["frames"])
    assert all(0 <= value <= 1 for frame in heatmap["frames"] for value in frame)


def test_heatmap_shows_the_snowy_area(providers):
    heatmap = post().json()["heatmap"]
    first_frame = dict(zip(map(tuple, heatmap["points"]), heatmap["frames"][0]))

    snowy = [value for (lat, _), value in first_frame.items() if lat > 0.1]
    calm = [value for (lat, _), value in first_frame.items() if lat <= 0.1]
    assert snowy and calm
    assert min(snowy) > 0.75  # Severe snow: score 3.5 of 4
    assert max(calm) < 0.25  # 10 mph gusts: still within Low


def test_vehicle_weight_adds_tare_to_load():
    assert trip_planner.vehicle_weight_kg(45_000) == round(80_000 * 0.45359237)


# --- validation -------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"departure_time": departure(-2)}, "departure_time"),
        ({"departure_time": departure(24 * 8)}, "departure_time"),
        ({"departure_time": "tomorrow"}, "departure_time"),
        ({"load_weight_lb": 0}, "load_weight_lb"),
        ({"load_weight_lb": 80_001}, "load_weight_lb"),
        ({"interval_miles": 15}, "interval_miles"),
        ({"origin": {"label": "X", "lat": 95, "lon": 0}}, "origin"),
        ({"destination": None}, "destination"),
    ],
)
def test_invalid_requests_are_rejected(providers, overrides, field):
    response = post(**overrides)

    assert response.status_code == 400
    assert field in response.json()


def test_same_origin_and_destination_is_rejected(providers):
    response = post(destination=ORIGIN)

    assert response.status_code == 400
    assert "non_field_errors" in response.json()


# --- provider errors --------------------------------------------------------


def test_no_route_returns_422(providers):
    providers(routes=NoRouteFound("No truck route found."))

    response = post()

    assert response.status_code == 422
    assert response.json() == {"code": "no_route", "detail": "No truck route found."}


def test_upstream_failure_returns_502(providers):
    def failing_weather(*args):
        raise UpstreamError("open_meteo", 503)

    providers(weather=failing_weather)

    response = post()

    assert response.status_code == 502
    assert response.json()["code"] == "upstream_error"
    assert response.json()["provider"] == "open_meteo"


# --- geocode ----------------------------------------------------------------


def test_geocode_returns_places(monkeypatch):
    monkeypatch.setattr("trips.views.tomtom.search_places", lambda q: [Place("Dallas, TX", 32.78, -96.8)])

    response = Client().get("/api/geocode", {"q": "dallas"})

    assert response.status_code == 200
    assert response.json() == {"results": [{"label": "Dallas, TX", "lat": 32.78, "lon": -96.8}]}


def test_geocode_requires_a_query():
    response = Client().get("/api/geocode", {"q": "d"})

    assert response.status_code == 400
