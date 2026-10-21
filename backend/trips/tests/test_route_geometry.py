import pytest

from trips.domain.route_geometry import detour_point, shared_fraction

EASTBOUND = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]


def test_detour_point_left_of_travel_direction():
    # Travelling east along the equator, left is north.
    assert detour_point((0.0, 0.0), (0.0, 2.0), 0.15) == pytest.approx((0.3, 1.0))


def test_detour_point_right_of_travel_direction():
    assert detour_point((0.0, 0.0), (0.0, 2.0), -0.15) == pytest.approx((-0.3, 1.0))


def test_detour_point_northbound_goes_west_on_the_left():
    lat, lon = detour_point((30.0, -100.0), (40.0, -100.0), 0.15)

    assert lat == pytest.approx(35.0)
    assert lon < -100.0


def test_identical_routes_are_fully_shared():
    assert shared_fraction(EASTBOUND, EASTBOUND) == pytest.approx(1.0)


def test_far_apart_routes_share_nothing():
    parallel = [(1.0, 0.0), (1.0, 2.0)]  # ~69 mi north

    assert shared_fraction(parallel, EASTBOUND) == pytest.approx(0.0)


def test_route_that_splits_is_partly_shared():
    # Shares its first leg (1 of ~2.41 degrees of length), then heads north-east.
    split = [(0.0, 0.0), (0.0, 1.0), (1.0, 2.0)]

    assert shared_fraction(split, EASTBOUND) == pytest.approx(0.42, abs=0.03)
