"""Open-Meteo hourly forecast client (no API key needed).

Docs: https://open-meteo.com/en/docs
Many locations go in one request (comma-separated coordinates), in batches
sent in parallel. The free tier counts every location as one API call, so
each point's forecast is cached on its own and only missing points are
fetched. Hourly precipitation is the amount over the preceding hour, so it is
already an hourly rate (in/hr with precipitation_unit=inch).
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import requests
from django.core.cache import cache

from trips.domain.sampling import LatLon
from trips.exceptions import UpstreamError

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PROVIDER = "open_meteo"
TIMEOUT_SECONDS = 30
HOURLY_VARIABLES = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"
MAX_LOCATIONS_PER_REQUEST = 100
MAX_PARALLEL_REQUESTS = 4
CACHE_SECONDS = 30 * 60
# ~1 km; finer than the weather models' grid, and makes cache hits likely.
COORDINATE_DECIMALS = 2


@dataclass(frozen=True)
class WeatherSample:
    time: datetime
    wind_mph: float
    gust_mph: float
    rain_in_hr: float  # rain + showers
    snow_in_hr: float


@dataclass(frozen=True)
class HourlyForecast:
    samples: list[WeatherSample]  # one per hour, ascending

    def at(self, when: datetime) -> WeatherSample:
        """The forecast hour closest to `when`."""
        return min(self.samples, key=lambda sample: abs(sample.time - when))


def hourly_forecasts(points: list[LatLon], start: datetime, end: datetime) -> list[HourlyForecast]:
    """Hourly forecasts covering [start, end] for each point, in the same order."""
    start_hour = _floor_hour(start)
    end_hour = _ceil_hour(end)
    rounded = [(round(lat, COORDINATE_DECIMALS), round(lon, COORDINATE_DECIMALS)) for lat, lon in points]

    keys = {point: _cache_key(point, start_hour, end_hour) for point in rounded}
    found = cache.get_many(keys.values())
    missing = [point for point, key in keys.items() if key not in found]
    batches = [missing[i : i + MAX_LOCATIONS_PER_REQUEST] for i in range(0, len(missing), MAX_LOCATIONS_PER_REQUEST)]

    if batches:
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REQUESTS) as pool:
            results = list(pool.map(lambda batch: _fetch_batch(batch, start_hour, end_hour), batches))
        fetched = {
            keys[point]: forecast
            for batch, forecasts in zip(batches, results)
            for point, forecast in zip(batch, forecasts)
        }
        cache.set_many(fetched, CACHE_SECONDS)
        found.update(fetched)

    return [found[keys[point]] for point in rounded]


def _fetch_batch(points: list[LatLon], start: datetime, end: datetime) -> list[HourlyForecast]:
    params = {
        "latitude": ",".join(str(lat) for lat, _ in points),
        "longitude": ",".join(str(lon) for _, lon in points),
        "hourly": HOURLY_VARIABLES,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        "timeformat": "unixtime",
        "start_hour": start.strftime("%Y-%m-%dT%H:%M"),
        "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
    }
    try:
        response = requests.get(FORECAST_URL, params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException:
        raise UpstreamError(PROVIDER) from None
    if not response.ok:
        raise UpstreamError(PROVIDER, response.status_code)

    data = response.json()
    locations = data if isinstance(data, list) else [data]  # a single point returns an object
    return [_parse_location(location["hourly"]) for location in locations]


def _parse_location(hourly: dict) -> HourlyForecast:
    # Missing values (null) are treated as no wind / no precipitation.
    def values(name: str) -> list[float]:
        return [value or 0.0 for value in hourly[name]]

    samples = [
        WeatherSample(
            time=datetime.fromtimestamp(timestamp, UTC),
            wind_mph=wind,
            gust_mph=gust,
            rain_in_hr=rain + showers,
            snow_in_hr=snow,
        )
        for timestamp, wind, gust, rain, showers, snow in zip(
            hourly["time"],
            values("wind_speed_10m"),
            values("wind_gusts_10m"),
            values("rain"),
            values("showers"),
            values("snowfall"),
        )
    ]
    return HourlyForecast(samples)


def _floor_hour(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _ceil_hour(moment: datetime) -> datetime:
    floor = _floor_hour(moment)
    return floor if floor == moment else floor + timedelta(hours=1)


def _cache_key(point: LatLon, start: datetime, end: datetime) -> str:
    lat, lon = point
    return f"open-meteo:{lat}:{lon}:{start:%Y%m%d%H}:{end:%Y%m%d%H}"
