from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from trips.domain.sampling import INTERVAL_OPTIONS

MAX_LOAD_WEIGHT_LB = 80_000
DEPARTURE_MAX_PAST = timedelta(hours=1)
# Keeps the trip plus the 48 h heatmap inside Open-Meteo's 16-day forecast.
DEPARTURE_MAX_FUTURE = timedelta(days=7)
AUTO_INTERVAL = "auto"


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=200)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class TripPlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure_time = serializers.DateTimeField()
    load_weight_lb = serializers.FloatField(min_value=1, max_value=MAX_LOAD_WEIGHT_LB)
    interval_miles = serializers.ChoiceField(
        choices=[AUTO_INTERVAL, *INTERVAL_OPTIONS], required=False, default=AUTO_INTERVAL
    )

    def validate_departure_time(self, value):
        now = timezone.now()
        if value < now - DEPARTURE_MAX_PAST:
            raise serializers.ValidationError("Departure cannot be in the past.")
        if value > now + DEPARTURE_MAX_FUTURE:
            raise serializers.ValidationError("Departure must be within the next 7 days (forecast range).")
        return value

    def validate_interval_miles(self, value):
        return None if value == AUTO_INTERVAL else int(value)

    def validate(self, data):
        origin, destination = data["origin"], data["destination"]
        if (origin["lat"], origin["lon"]) == (destination["lat"], destination["lon"]):
            raise serializers.ValidationError("Origin and destination must be different.")
        return data


class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=200)
