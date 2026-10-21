import pytest
from shapely.geometry import LineString, Point

from trips.domain.heatmap_grid import CORRIDOR_BUFFER_MILES, MAX_GRID_POINTS, corridor_grid
from trips.domain.route_geometry import MILES_PER_DEGREE_LAT

# Roughly Dallas -> Denver (~800 mi) and Austin -> San Antonio (~80 mi).
LONG_ROUTES = [
    [(32.78, -96.80), (35.20, -101.83), (39.74, -104.98)],
    [(32.78, -96.80), (35.47, -97.52), (37.69, -97.34), (39.74, -104.98)],
]
SHORT_ROUTE = [[(30.27, -97.74), (29.42, -98.49)]]


def test_grid_stays_within_the_point_budget():
    grid = corridor_grid(LONG_ROUTES)

    assert 0 < len(grid.points) <= MAX_GRID_POINTS


def test_long_trips_use_a_coarser_step_than_short_trips():
    assert corridor_grid(LONG_ROUTES).step_degrees > corridor_grid(SHORT_ROUTE).step_degrees


def test_points_lie_on_the_global_lattice():
    grid = corridor_grid(LONG_ROUTES)

    for lat, lon in grid.points:
        assert lat / grid.step_degrees == pytest.approx(round(lat / grid.step_degrees))
        assert lon / grid.step_degrees == pytest.approx(round(lon / grid.step_degrees))


def test_points_lie_inside_the_corridor():
    grid = corridor_grid(SHORT_ROUTE)
    route = LineString([(lon, lat) for lat, lon in SHORT_ROUTE[0]])
    # Unprojected degrees overstate east-west distance, so allow the longitude factor.
    max_distance = CORRIDOR_BUFFER_MILES / MILES_PER_DEGREE_LAT / 0.86

    assert all(route.distance(Point(lon, lat)) <= max_distance for lat, lon in grid.points)


def test_corridor_covers_the_whole_route():
    grid = corridor_grid(SHORT_ROUTE)
    lats = [lat for lat, _ in grid.points]

    assert min(lats) < 29.42 and max(lats) > 30.27


def test_same_trip_gives_the_same_grid():
    assert corridor_grid(LONG_ROUTES) == corridor_grid(LONG_ROUTES)
