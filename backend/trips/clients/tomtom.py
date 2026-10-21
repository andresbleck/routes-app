"""TomTom Search (geocoding) and Routing (truck mode) client.

Docs: https://developer.tomtom.com/search-api/documentation
      https://developer.tomtom.com/routing-api/documentation
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

import requests
from django.conf import settings

from trips.domain.sampling import LatLon, cumulative_miles, seconds_from_anchors
from trips.exceptions import NoRouteFound, UpstreamError

BASE_URL = "https://api.tomtom.com"
PROVIDER = "tomtom"
TIMEOUT_SECONDS = 30
METERS_PER_MILE = 1609.344
# Cities, postal addresses, address ranges and streets (no POIs).
SEARCH_INDEXES = "Geo,PAD,Addr,Str"


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float


@dataclass(frozen=True)
class TruckRoute:
    points: list[LatLon]
    cumulative_seconds: list[float]  # driving time from the origin at each point
    distance_miles: float
    duration_seconds: float


def search_places(query: str, limit: int = 5) -> list[Place]:
    data = _get(
        f"/search/2/search/{quote(query)}.json",
        {"limit": limit, "countrySet": "US", "typeahead": "true", "idxSet": SEARCH_INDEXES},
    )
    return [
        Place(
            label=item["address"]["freeformAddress"],
            lat=item["position"]["lat"],
            lon=item["position"]["lon"],
        )
        for item in data["results"]
    ]


def truck_routes(
    locations: list[LatLon],
    departure: datetime,
    vehicle_weight_kg: int,
    max_alternatives: int = 0,
) -> list[TruckRoute]:
    """Truck routes through `locations` (origin, optional via points, destination)."""
    params = {
        "travelMode": "truck",
        "vehicleCommercial": "true",
        "vehicleWeight": vehicle_weight_kg,
        "traffic": "true",
        "instructionsType": "coded",
    }
    if max_alternatives:
        params["maxAlternatives"] = max_alternatives
    # TomTom only accepts future departures; otherwise it routes for "now".
    if departure > datetime.now(UTC):
        params["departAt"] = departure.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    path = ":".join(f"{lat},{lon}" for lat, lon in locations)
    try:
        data = _get(f"/routing/1/calculateRoute/{path}/json", params)
    except UpstreamError as error:
        if error.status_code == 400:
            raise NoRouteFound("No truck route found between these locations.") from None
        raise
    return [_parse_route(route) for route in data["routes"]]


def _parse_route(route: dict) -> TruckRoute:
    # Leg points are concatenated; instruction point indexes refer to this list.
    points = [(p["latitude"], p["longitude"]) for leg in route["legs"] for p in leg["points"]]
    summary = route["summary"]

    anchors = {0: 0.0, len(points) - 1: float(summary["travelTimeInSeconds"])}
    for instruction in route["guidance"]["instructions"]:
        anchors[instruction["pointIndex"]] = float(instruction["travelTimeInSeconds"])

    return TruckRoute(
        points=points,
        cumulative_seconds=seconds_from_anchors(cumulative_miles(points), sorted(anchors.items())),
        distance_miles=summary["lengthInMeters"] / METERS_PER_MILE,
        duration_seconds=float(summary["travelTimeInSeconds"]),
    )


def _get(path: str, params: dict) -> dict:
    try:
        response = requests.get(
            BASE_URL + path,
            params={"key": settings.TOMTOM_API_KEY, **params},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        # `from None`: the original message contains the URL with the API key.
        raise UpstreamError(PROVIDER) from None
    if not response.ok:
        raise UpstreamError(PROVIDER, response.status_code)
    return response.json()
