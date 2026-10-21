from django.urls import path

from trips import views

urlpatterns = [
    path("health", views.HealthView.as_view(), name="health"),
    path("geocode", views.GeocodeView.as_view(), name="geocode"),
    path("trips/plan", views.TripPlanView.as_view(), name="trip-plan"),
    path("trips/plan/<uuid:plan_id>/weather", views.TripWeatherView.as_view(), name="trip-weather"),
]
