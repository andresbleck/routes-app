from datetime import UTC, datetime

import pytest

from trips.clients.tomtom import TruckRoute
from trips.domain.route_geometry import detour_point
from trips.exceptions import NoRouteFound
from trips.services import route_options

ORIGIN, DESTINATION = (0.0, 0.0), (0.0, 2.0)
DEPARTURE = datetime(2026, 10, 21, 13, 0, tzinfo=UTC)
LEFT_15, RIGHT_15, LEFT_30, RIGHT_30 = route_options.DETOUR_OFFSETS


def make_route(points, hours=2.0):
    return TruckRoute(points=points, cumulative_seconds=[0.0] * len(points), distance_miles=0, duration_seconds=hours * 3600)


DIRECT = make_route([ORIGIN, DESTINATION])
NORTH = make_route([ORIGIN, (0.5, 1.0), DESTINATION])
SOUTH = make_route([ORIGIN, (-0.5, 1.0), DESTINATION])
FAR_SOUTH = make_route([ORIGIN, (-0.8, 1.0), DESTINATION])


class FakeTomTom:
    """Answers the direct request with `provider_routes` and each detour
    request with the result configured for its offset (default: no route).
    Detours run in parallel, so results are looked up by via point."""

    def __init__(self, provider_routes, detours):
        self.provider_routes = provider_routes
        self.detours = {detour_point(ORIGIN, DESTINATION, offset): result for offset, result in detours.items()}
        self.calls = []

    def truck_routes(self, locations, departure, vehicle_weight_kg, max_alternatives=0):
        self.calls.append(locations)
        if len(locations) == 2:
            return self.provider_routes
        result = self.detours.get(locations[1], NoRouteFound())
        if isinstance(result, Exception):
            raise result
        return [result]


@pytest.fixture
def fake(monkeypatch):
    def install(provider_routes, detours=None):
        tomtom = FakeTomTom(provider_routes, detours or {})
        monkeypatch.setattr(route_options.tomtom, "truck_routes", tomtom.truck_routes)
        return tomtom

    return install


def get_options():
    return route_options.get_route_options(ORIGIN, DESTINATION, DEPARTURE, vehicle_weight_kg=34_000)


def test_three_provider_routes_need_no_detour(fake):
    tomtom = fake([DIRECT, NORTH, SOUTH])

    routes, warnings = get_options()

    assert routes == [DIRECT, NORTH, SOUTH]
    assert warnings == []
    assert len(tomtom.calls) == 1


def test_missing_route_is_generated_through_a_detour(fake):
    tomtom = fake([DIRECT, NORTH], detours={RIGHT_15: SOUTH})

    routes, warnings = get_options()

    assert routes == [DIRECT, NORTH, SOUTH]
    assert warnings == ["The routing provider returned 2 route(s); 1 more generated through a detour waypoint."]
    assert len(tomtom.calls) == 1 + len(route_options.DETOUR_OFFSETS)


def test_detours_are_preferred_in_offset_order(fake):
    fake([DIRECT, NORTH], detours={RIGHT_15: SOUTH, RIGHT_30: FAR_SOUTH})

    routes, _ = get_options()

    assert routes[-1] == SOUTH


def test_duplicate_detour_is_skipped(fake):
    duplicate_of_north = make_route([ORIGIN, (0.5, 1.0), DESTINATION])
    fake([DIRECT, NORTH], detours={LEFT_15: duplicate_of_north, RIGHT_15: SOUTH})

    routes, _ = get_options()

    assert routes[-1] == SOUTH


def test_much_slower_detour_is_rejected(fake):
    slow = make_route([ORIGIN, (-0.5, 1.0), DESTINATION], hours=3.5)  # 1.75x the fastest
    fake([DIRECT, NORTH], detours={LEFT_15: slow, RIGHT_30: FAR_SOUTH})

    routes, _ = get_options()

    assert routes[-1] == FAR_SOUTH


def test_single_route_gets_two_detours(fake):
    fake([DIRECT], detours={LEFT_15: NORTH, RIGHT_15: SOUTH})

    routes, warnings = get_options()

    assert routes == [DIRECT, NORTH, SOUTH]
    assert "1 route(s); 2 more generated" in warnings[0]


def test_warns_when_fewer_than_three_routes_exist(fake):
    fake([DIRECT, NORTH])  # every detour is unreachable

    routes, warnings = get_options()

    assert routes == [DIRECT, NORTH]
    assert warnings == ["Only 2 distinct route(s) could be found for this trip."]
