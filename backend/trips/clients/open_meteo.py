"""Open-Meteo hourly forecasts, fetched by the user's browser.

Docs: https://open-meteo.com/en/docs
Open-Meteo's free tier is rate-limited per IP, and the shared outbound IPs of
cloud hosts are often over the limit. So the backend builds the request URLs,
the browser fetches them (from the user's own IP), and posts the responses
back to be parsed here. Many locations go in one request, in batches.
Hourly precipitation is the amount over the preceding hour, so it is already
an hourly rate (in/hr with precipitation_unit=inch).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from trips.domain.sampling import LatLon

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall")
MAX_LOCATIONS_PER_REQUEST = 100
# ~1 km; finer than the weather models' grid.
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

    @property
    def last_time(self) -> datetime:
        return self.samples[-1].time


def round_point(point: LatLon) -> LatLon:
    lat, lon = point
    return (round(lat, COORDINATE_DECIMALS), round(lon, COORDINATE_DECIMALS))


def forecast_urls(points: list[LatLon], start: datetime, end: datetime) -> list[str]:
    """Request URLs covering [start, end] for `points`, in batches. The
    responses, concatenated in order, give one location per point."""
    common = {
        "hourly": ",".join(HOURLY_VARIABLES),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        "timeformat": "unixtime",
        "start_hour": _floor_hour(start).strftime("%Y-%m-%dT%H:%M"),
        "end_hour": _ceil_hour(end).strftime("%Y-%m-%dT%H:%M"),
    }
    urls = []
    for i in range(0, len(points), MAX_LOCATIONS_PER_REQUEST):
        batch = points[i : i + MAX_LOCATIONS_PER_REQUEST]
        coordinates = {
            "latitude": ",".join(str(lat) for lat, _ in batch),
            "longitude": ",".join(str(lon) for _, lon in batch),
        }
        urls.append(f"{FORECAST_URL}?{urlencode(coordinates | common, safe=',:')}")
    return urls


def parse_locations(locations: list[dict]) -> list[HourlyForecast]:
    """Parse Open-Meteo locations ({"hourly": {...}}), one forecast each.
    The data comes through the browser, so anything malformed raises ValueError."""
    try:
        return [_parse_hourly(location["hourly"]) for location in locations]
    except (KeyError, TypeError, OverflowError, OSError) as error:
        raise ValueError("Malformed Open-Meteo data.") from error


def _parse_hourly(hourly: dict) -> HourlyForecast:
    # Missing values (null) are treated as no wind / no precipitation.
    def values(name: str) -> list[float]:
        return [float(value or 0.0) for value in hourly[name]]

    columns = [values(name) for name in HOURLY_VARIABLES]
    if not hourly["time"] or any(len(column) != len(hourly["time"]) for column in columns):
        raise ValueError("Hourly arrays must be non-empty and the same length.")

    samples = [
        WeatherSample(
            time=datetime.fromtimestamp(int(timestamp), UTC),
            wind_mph=wind,
            gust_mph=gust,
            rain_in_hr=rain + showers,
            snow_in_hr=snow,
        )
        for timestamp, wind, gust, rain, showers, snow in zip(hourly["time"], *columns)
    ]
    return HourlyForecast(samples)


def _floor_hour(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _ceil_hour(moment: datetime) -> datetime:
    floor = _floor_hour(moment)
    return floor if floor == moment else floor + timedelta(hours=1)
