import re
from datetime import UTC, datetime, timedelta

import pytest
import requests
import responses

from trips.clients import tomtom
from trips.exceptions import NoRouteFound, UpstreamError

ROUTE_URL = re.compile(r"https://api\.tomtom\.com/routing/1/calculateRoute/.*")
SEARCH_URL = re.compile(r"https://api\.tomtom\.com/search/2/search/.*")
ORIGIN, DESTINATION = (0.0, 0.0), (0.0, 2.0)
FUTURE = datetime.now(UTC) + timedelta(days=1)


def route_payload(legs, instructions, seconds=7200, meters=222_640):
    return {
        "summary": {"lengthInMeters": meters, "travelTimeInSeconds": seconds},
        "legs": [{"points": [{"latitude": lat, "longitude": lon} for lat, lon in leg]} for leg in legs],
        "guidance": {
            "instructions": [{"pointIndex": index, "travelTimeInSeconds": time} for index, time in instructions]
        },
    }


def query(call):
    return call.request.params


@responses.activate
def test_search_places_returns_labels_and_coordinates():
    responses.get(
        SEARCH_URL,
        json={
            "results": [
                {"address": {"freeformAddress": "Dallas, TX"}, "position": {"lat": 32.78, "lon": -96.8}},
                {"address": {"freeformAddress": "Dallas, GA"}, "position": {"lat": 33.92, "lon": -84.84}},
            ]
        },
    )

    places = tomtom.search_places("dallas")

    assert places == [tomtom.Place("Dallas, TX", 32.78, -96.8), tomtom.Place("Dallas, GA", 33.92, -84.84)]
    assert query(responses.calls[0])["countrySet"] == "US"


@responses.activate
def test_truck_routes_sends_truck_parameters():
    responses.get(ROUTE_URL, json={"routes": [route_payload([[ORIGIN, DESTINATION]], [(0, 0)])]})

    tomtom.truck_routes([ORIGIN, DESTINATION], FUTURE, vehicle_weight_kg=34_000, max_alternatives=2)

    params = query(responses.calls[0])
    assert params["travelMode"] == "truck"
    assert params["vehicleWeight"] == "34000"
    assert params["maxAlternatives"] == "2"
    assert params["departAt"] == FUTURE.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert "/0.0,0.0:0.0,2.0/json" in responses.calls[0].request.url


@responses.activate
def test_past_departure_is_not_sent():
    responses.get(ROUTE_URL, json={"routes": [route_payload([[ORIGIN, DESTINATION]], [(0, 0)])]})

    tomtom.truck_routes([ORIGIN, DESTINATION], datetime.now(UTC) - timedelta(minutes=5), 34_000)

    assert "departAt" not in query(responses.calls[0])
    assert "maxAlternatives" not in query(responses.calls[0])


@responses.activate
def test_route_parsing_joins_legs_and_uses_instruction_times():
    # Two legs (via point at lon 1.0); the junction point appears in both legs.
    legs = [[(0.0, 0.0), (0.0, 1.0)], [(0.0, 1.0), (0.0, 2.0)]]
    # Reaching the via point takes 1 h of the 3 h total.
    responses.get(ROUTE_URL, json={"routes": [route_payload(legs, [(0, 0), (1, 3600)], seconds=10_800)]})

    [route] = tomtom.truck_routes([ORIGIN, (0.0, 1.0), DESTINATION], FUTURE, 34_000)

    assert route.points == [(0.0, 0.0), (0.0, 1.0), (0.0, 1.0), (0.0, 2.0)]
    assert route.cumulative_seconds == pytest.approx([0, 3600, 3600, 10_800])
    assert route.duration_seconds == 10_800
    assert route.distance_miles == pytest.approx(222_640 / 1609.344)


@responses.activate
def test_returns_every_route_from_the_provider():
    payload = route_payload([[ORIGIN, DESTINATION]], [(0, 0)])
    responses.get(ROUTE_URL, json={"routes": [payload, payload, payload]})

    routes = tomtom.truck_routes([ORIGIN, DESTINATION], FUTURE, 34_000, max_alternatives=2)

    assert len(routes) == 3


@responses.activate
def test_bad_request_means_no_route():
    responses.get(ROUTE_URL, status=400, json={"detailedError": {"code": "NO_ROUTE_FOUND"}})

    with pytest.raises(NoRouteFound):
        tomtom.truck_routes([ORIGIN, DESTINATION], FUTURE, 34_000)


@responses.activate
def test_server_error_is_upstream_error():
    responses.get(ROUTE_URL, status=503)

    with pytest.raises(UpstreamError) as error:
        tomtom.truck_routes([ORIGIN, DESTINATION], FUTURE, 34_000)

    assert error.value.provider == "tomtom"
    assert error.value.status_code == 503


@responses.activate
def test_network_error_does_not_leak_api_key():
    responses.get(SEARCH_URL, body=requests.ConnectionError("failed for url ...?key=test-key"))

    with pytest.raises(UpstreamError) as error:
        tomtom.search_places("dallas")

    assert "test-key" not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True
