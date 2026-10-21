from datetime import UTC, datetime, timedelta

import pytest

from trips.domain.sampling import (
    cumulative_miles,
    haversine_miles,
    pick_interval,
    proportional_seconds,
    resolve_interval,
    sample_checkpoints,
    seconds_from_anchors,
)

DEPARTURE = datetime(2026, 10, 21, 13, 0, tzinfo=UTC)

# Two equal legs along the equator: ~69.17 mi per degree of longitude.
EQUATOR_ROUTE = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
LEG_MILES = haversine_miles((0.0, 0.0), (0.0, 1.0))


def test_haversine_one_degree_of_latitude():
    assert haversine_miles((0.0, 0.0), (1.0, 0.0)) == pytest.approx(69.09, abs=0.01)


def test_cumulative_miles():
    assert cumulative_miles(EQUATOR_ROUTE) == pytest.approx([0, LEG_MILES, 2 * LEG_MILES])


def test_proportional_seconds_assumes_constant_speed():
    assert proportional_seconds([0, 25, 100], 3600) == pytest.approx([0, 900, 3600])


def test_seconds_from_anchors_spreads_time_by_distance():
    miles = [0, 10, 30, 40, 70]
    # Known times at vertices 0, 2 and 4.
    anchors = [(0, 0), (2, 600), (4, 4200)]

    # Vertex 3 is 10 of the 40 miles between anchors 2 and 4: 600 + 3600 / 4.
    assert seconds_from_anchors(miles, anchors) == pytest.approx([0, 200, 600, 1500, 4200])


def test_seconds_from_anchors_with_zero_length_span():
    assert seconds_from_anchors([0, 0, 10], [(0, 0), (1, 0), (2, 60)]) == pytest.approx([0, 0, 60])


@pytest.mark.parametrize(
    ("route_miles", "expected"),
    [(5, 10), (150, 10), (151, 25), (600, 25), (601, 50), (2800, 50)],
)
def test_pick_interval(route_miles, expected):
    assert pick_interval(route_miles) == expected


@pytest.mark.parametrize(
    ("requested", "route_miles", "expected"),
    [
        (None, 400, 25),  # automatic
        (10, 400, 10),  # 41 checkpoints, within the cap
        (10, 1000, 25),  # 101 checkpoints would exceed the cap
        (25, 2500, 50),  # 101 checkpoints would exceed the cap
        (50, 5000, 50),  # already the widest option
    ],
)
def test_resolve_interval(requested, route_miles, expected):
    assert resolve_interval(requested, route_miles) == expected


def test_checkpoints_every_interval_plus_destination():
    checkpoints = sample_checkpoints(EQUATOR_ROUTE, [0, 3600, 7200], 25, DEPARTURE)

    distances = [c.distance_miles for c in checkpoints]
    assert distances == pytest.approx([0, 25, 50, 75, 100, 125, 2 * LEG_MILES])
    assert [c.index for c in checkpoints] == list(range(7))


def test_checkpoint_positions_are_interpolated_along_the_route():
    checkpoints = sample_checkpoints(EQUATOR_ROUTE, [0, 3600, 7200], 25, DEPARTURE)

    assert (checkpoints[0].lat, checkpoints[0].lon) == (0.0, 0.0)
    assert checkpoints[1].lon == pytest.approx(25 / LEG_MILES)
    assert (checkpoints[-1].lat, checkpoints[-1].lon) == pytest.approx((0.0, 2.0))


def test_eta_follows_provider_times_with_non_uniform_speed():
    # First leg takes 1 h, second leg takes 3 h.
    checkpoints = sample_checkpoints(EQUATOR_ROUTE, [0, 3600, 4 * 3600], 25, DEPARTURE)
    by_distance = {round(c.distance_miles): c for c in checkpoints}

    assert by_distance[0].eta == DEPARTURE
    assert by_distance[50].eta == DEPARTURE + timedelta(seconds=3600 * 50 / LEG_MILES)
    expected_100 = 3600 + 3 * 3600 * (100 - LEG_MILES) / LEG_MILES
    assert (by_distance[100].eta - DEPARTURE).total_seconds() == pytest.approx(expected_100)
    assert checkpoints[-1].eta == DEPARTURE + timedelta(hours=4)


def test_segment_miles_add_up_to_route_length():
    checkpoints = sample_checkpoints(EQUATOR_ROUTE, [0, 3600, 7200], 25, DEPARTURE)

    assert sum(c.segment_miles for c in checkpoints) == pytest.approx(2 * LEG_MILES)
    assert checkpoints[0].segment_miles == pytest.approx(12.5)
    assert checkpoints[1].segment_miles == pytest.approx(25)


def test_route_shorter_than_interval_has_origin_and_destination():
    route = [(0.0, 0.0), (0.0, 0.1)]  # ~6.9 mi

    checkpoints = sample_checkpoints(route, [0, 600], 10, DEPARTURE)

    assert len(checkpoints) == 2
    assert checkpoints[-1].eta == DEPARTURE + timedelta(seconds=600)


def test_route_length_multiple_of_interval_has_no_duplicate_destination():
    route = [(0.0, 0.0), (0.0, 50 / LEG_MILES)]  # exactly 50 mi

    checkpoints = sample_checkpoints(route, [0, 3600], 25, DEPARTURE)

    assert [c.distance_miles for c in checkpoints] == pytest.approx([0, 25, 50])


def test_duplicate_vertices_do_not_break_sampling():
    route = [(0.0, 0.0), (0.0, 1.0), (0.0, 1.0), (0.0, 2.0)]

    checkpoints = sample_checkpoints(route, [0, 3600, 3600, 7200], 25, DEPARTURE)

    assert len(checkpoints) == 7
    assert checkpoints[-1].eta == DEPARTURE + timedelta(hours=2)
