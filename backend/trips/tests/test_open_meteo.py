from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from trips.clients import open_meteo

START = datetime(2026, 10, 21, 13, 0, tzinfo=UTC)


def location(hours=3, gusts=None, rain=None, showers=None, snow=None):
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


def query(url):
    return parse_qs(urlparse(url).query)


# --- forecast_urls ----------------------------------------------------------


def test_url_uses_imperial_units_variables_and_hour_window():
    [url] = open_meteo.forecast_urls([(32.78, -96.8)], START + timedelta(minutes=20), START + timedelta(hours=1, minutes=5))

    params = query(url)
    assert url.startswith(open_meteo.FORECAST_URL + "?")
    assert params["latitude"] == ["32.78"]
    assert params["longitude"] == ["-96.8"]
    assert params["wind_speed_unit"] == ["mph"]
    assert params["precipitation_unit"] == ["inch"]
    assert params["hourly"] == ["wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"]
    assert params["start_hour"] == ["2026-10-21T13:00"]  # floored
    assert params["end_hour"] == ["2026-10-21T15:00"]  # ceiled


def test_many_points_are_split_into_batches_in_order():
    points = [(float(i), 0.0) for i in range(150)]

    urls = open_meteo.forecast_urls(points, START, START + timedelta(hours=2))

    assert len(urls) == 2
    latitudes = [lat for url in urls for lat in query(url)["latitude"][0].split(",")]
    assert latitudes == [str(float(i)) for i in range(150)]


def test_round_point_keeps_about_one_km():
    assert open_meteo.round_point((32.77763, -96.79689)) == (32.78, -96.8)


# --- parse_locations --------------------------------------------------------


def test_locations_are_parsed_in_order():
    forecasts = open_meteo.parse_locations([location(gusts=[1.0] * 3), location(gusts=[2.0] * 3)])

    assert [f.samples[0].gust_mph for f in forecasts] == [1.0, 2.0]
    assert [s.time for s in forecasts[0].samples] == [START + timedelta(hours=h) for h in range(3)]
    assert forecasts[0].last_time == START + timedelta(hours=2)


def test_rain_includes_showers_and_nulls_become_zero():
    [forecast] = open_meteo.parse_locations([location(rain=[0.1, None, 0.0], showers=[0.05, 0.2, None])])

    assert [s.rain_in_hr for s in forecast.samples] == pytest.approx([0.15, 0.2, 0.0])


def test_at_picks_the_closest_forecast_hour():
    [forecast] = open_meteo.parse_locations([location(gusts=[10.0, 30.0, 50.0])])

    assert forecast.at(START + timedelta(minutes=29)).gust_mph == 10.0
    assert forecast.at(START + timedelta(minutes=31)).gust_mph == 30.0
    assert forecast.at(START + timedelta(hours=5)).gust_mph == 50.0


@pytest.mark.parametrize(
    "bad_location",
    [
        {},  # no hourly block
        {"hourly": {"time": []}},  # missing variables
        {"hourly": {**location()["hourly"], "rain": [0.0]}},  # arrays of different length
        {"hourly": {**location()["hourly"], "time": []}},  # no hours
        {"hourly": {**location()["hourly"], "wind_gusts_10m": ["fast", 1, 2]}},  # not a number
        {"hourly": {**location()["hourly"], "time": [10**20, 0, 1]}},  # impossible timestamp
        "not an object",
    ],
)
def test_malformed_locations_raise_value_error(bad_location):
    with pytest.raises(ValueError):
        open_meteo.parse_locations([bad_location])
