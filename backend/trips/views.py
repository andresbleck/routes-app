import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from trips.clients import tomtom
from trips.exceptions import NoRouteFound, UpstreamError
from trips.serializers import GeocodeQuerySerializer, TripPlanRequestSerializer
from trips.services.trip_planner import plan_trip

logger = logging.getLogger(__name__)


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
    def post(self, request):
        trip = TripPlanRequestSerializer(data=request.data)
        trip.is_valid(raise_exception=True)
        data = trip.validated_data
        try:
            plan = plan_trip(
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
        return Response(plan)


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
