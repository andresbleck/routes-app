import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def isolated_settings(settings):
    settings.TOMTOM_API_KEY = "test-key"
    cache.clear()
