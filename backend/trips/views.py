import logging
from uuid import uuid4

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from trips.clients import open_meteo, tomtom
from trips.exceptions import NoRouteFound, UpstreamError
from trips.serializers import GeocodeQuerySerializer, TripPlanRequestSerializer, TripWeatherSerializer
from trips.services.trip_planner import finish_plan, prepare_plan

logger = logging.getLogger(__name__)

PENDING_PLAN_SECONDS = 30 * 60


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


class GeocodeView(APIView):
    def get(self, request):
        query = GeocodeQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            places = tomtom.search_places(query.validated_data["q"])
        except UpstreamError as error:
            return _upstream_error_response(error)
        return Response({"results": [{"label": p.label, "lat": p.lat, "lon": p.lon} for p in places]})


class TripPlanView(APIView):
    """Step 1: routes and checkpoints. Returns the weather URLs for the browser to fetch."""

    def post(self, request):
        trip = TripPlanRequestSerializer(data=request.data)
        trip.is_valid(raise_exception=True)
        data = trip.validated_data
        try:
            pending = prepare_plan(
                origin=(data["origin"]["lat"], data["origin"]["lon"]),
                destination=(data["destination"]["lat"], data["destination"]["lon"]),
                departure=data["departure_time"],
                load_weight_lb=data["load_weight_lb"],
                requested_interval=data["interval_miles"],
            )
        except NoRouteFound as error:
            return Response({"code": "no_route", "detail": str(error)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except UpstreamError as error:
            return _upstream_error_response(error)

        plan_id = str(uuid4())
        cache.set(_pending_key(plan_id), pending, PENDING_PLAN_SECONDS)
        return Response({"plan_id": plan_id, "weather_urls": pending.weather_urls})


class TripWeatherView(APIView):
    """Step 2: the Open-Meteo responses fetched by the browser. Returns the full plan."""

    def post(self, request, plan_id):
        pending = cache.get(_pending_key(plan_id))
        if pending is None:
            return Response(
                {"code": "plan_expired", "detail": "This search expired. Please search again."},
                status=status.HTTP_404_NOT_FOUND,
            )

        body = TripWeatherSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        locations = body.validated_data["locations"]
        if len(locations) != len(pending.weather_points):
            return Response(
                {"locations": [f"Expected {len(pending.weather_points)} locations, got {len(locations)}."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            forecasts = open_meteo.parse_locations(locations)
        except ValueError:
            return Response({"locations": ["Malformed Open-Meteo data."]}, status=status.HTTP_400_BAD_REQUEST)

        return Response(finish_plan(pending, forecasts))


def _pending_key(plan_id) -> str:
    return f"pending-plan:{plan_id}"


def _upstream_error_response(error: UpstreamError) -> Response:
    logger.warning("Upstream error: %s", error)
    return Response(
        {
            "code": "upstream_error",
            "provider": error.provider,
            "detail": "A data provider is unavailable. Please try again in a moment.",
        },
        status=status.HTTP_502_BAD_GATEWAY,
    )
