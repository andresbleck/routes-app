import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from trips.clients import open_meteo
from trips.exceptions import UpstreamError

START = datetime(2026, 10, 21, 13, 0, tzinfo=UTC)


def hourly(hours=3, gusts=None, rain=None, showers=None, snow=None):
    times = [int((START + timedelta(hours=h)).timestamp()) for h in range(hours)]
    zeros = [0.0] * hours
    return {
        "hourly": {
            "time": times,
            "wind_speed_10m": [10.0] * hours,
            "wind_gusts_10m": gusts or [20.0] * hours,
            "rain": rain or zeros,
            "showers": showers or zeros,
            "snowfall": snow or zeros,
        }
    }


def query(call):
    return call.request.params


@responses.activate
def test_single_location_response_is_parsed():
    responses.get(open_meteo.FORECAST_URL, json=hourly())

    [forecast] = open_meteo.hourly_forecasts([(32.7763, -96.7969)], START, START + timedelta(hours=2))

    assert len(forecast.samples) == 3
    assert forecast.samples[0].time == START
    assert forecast.samples[0].gust_mph == 20.0


@responses.activate
def test_request_uses_imperial_units_and_hour_window():
    responses.get(open_meteo.FORECAST_URL, json=hourly())

    open_meteo.hourly_forecasts([(32.7763, -96.7969)], START + timedelta(minutes=20), START + timedelta(hours=1, minutes=5))

    params = query(responses.calls[0])
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert params["start_hour"] == "2026-10-21T13:00"  # floored
    assert params["end_hour"] == "2026-10-21T15:00"  # ceiled
    assert params["latitude"] == "32.78"  # rounded to ~1 km
    assert "wind_gusts_10m" in params["hourly"]


def gust_equals_latitude(request):
    """Fake server: each location's gust is its latitude, so results can be
    matched to points whatever order the parallel batches complete in."""
    latitudes = parse_qs(urlparse(request.url).query)["latitude"][0].split(",")
    return 200, {}, json.dumps([hourly(gusts=[float(lat)] * 3) for lat in latitudes])


@responses.activate
def test_many_locations_are_batched_and_keep_order():
    points = [(float(i), 0.0) for i in range(150)]
    responses.add_callback(responses.GET, open_meteo.FORECAST_URL, callback=gust_equals_latitude)

    forecasts = open_meteo.hourly_forecasts(points, START, START + timedelta(hours=2))

    assert len(responses.calls) == 2
    assert [f.samples[0].gust_mph for f in forecasts] == [float(i) for i in range(150)]


@responses.activate
def test_only_uncached_points_are_fetched_once_each():
    responses.add_callback(responses.GET, open_meteo.FORECAST_URL, callback=gust_equals_latitude)
    end = START + timedelta(hours=2)
    open_meteo.hourly_forecasts([(1.0, 0.0), (2.0, 0.0)], START, end)

    forecasts = open_meteo.hourly_forecasts([(2.0, 0.0), (3.0, 0.0), (3.0, 0.0)], START, end)

    assert [f.samples[0].gust_mph for f in forecasts] == [2.0, 3.0, 3.0]
    assert parse_qs(urlparse(responses.calls[1].request.url).query)["latitude"] == ["3.0"]


@responses.activate
def test_rain_includes_showers_and_nulls_become_zero():
    responses.get(open_meteo.FORECAST_URL, json=hourly(rain=[0.1, None, 0.0], showers=[0.05, 0.2, None]))

    [forecast] = open_meteo.hourly_forecasts([(0.0, 0.0)], START, START + timedelta(hours=2))

    assert [s.rain_in_hr for s in forecast.samples] == pytest.approx([0.15, 0.2, 0.0])


@responses.activate
def test_at_picks_the_closest_forecast_hour():
    responses.get(open_meteo.FORECAST_URL, json=hourly(gusts=[10.0, 30.0, 50.0]))
    [forecast] = open_meteo.hourly_forecasts([(0.0, 0.0)], START, START + timedelta(hours=2))

    assert forecast.at(START + timedelta(minutes=29)).gust_mph == 10.0
    assert forecast.at(START + timedelta(minutes=31)).gust_mph == 30.0
    assert forecast.at(START + timedelta(hours=5)).gust_mph == 50.0


@responses.activate
def test_repeated_requests_are_served_from_cache():
    responses.get(open_meteo.FORECAST_URL, json=hourly())

    for _ in range(2):
        open_meteo.hourly_forecasts([(0.0, 0.0)], START, START + timedelta(hours=2))

    assert len(responses.calls) == 1


@responses.activate
def test_error_status_is_upstream_error():
    responses.get(open_meteo.FORECAST_URL, status=429)

    with pytest.raises(UpstreamError) as error:
        open_meteo.hourly_forecasts([(0.0, 0.0)], START, START + timedelta(hours=2))

    assert error.value.provider == "open_meteo"
    assert error.value.status_code == 429
