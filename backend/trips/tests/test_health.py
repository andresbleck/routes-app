from django.test import Client


def test_health_returns_ok():
    response = Client().get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_allows_frontend_origin():
    response = Client().get("/api/health", HTTP_ORIGIN="http://localhost:5173")

    assert response["Access-Control-Allow-Origin"] == "http://localhost:5173"
