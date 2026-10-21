import itertools

import pytest

from trips.domain.risk import RiskLevel, classify_checkpoint, severity_score

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = RiskLevel


def classify(wind=0.0, rain=0.0, snow=0.0, load=0):
    return classify_checkpoint(wind_gust_mph=wind, rain_in_hr=rain, snow_in_hr=snow, load_weight_lb=load)


@pytest.mark.parametrize(
    ("wind", "expected"),
    [
        (0, LOW),
        (24.99, LOW),
        (25, MODERATE),
        (34.99, MODERATE),
        (35, HIGH),
        (44.99, HIGH),
        (45, SEVERE),
        (54.99, SEVERE),
        (55, NO_TRAVEL),
        (80, NO_TRAVEL),
    ],
)
def test_wind_gust_thresholds(wind, expected):
    assert classify(wind=wind).level == expected


@pytest.mark.parametrize(
    ("rain", "expected"),
    [
        (0, LOW),
        (0.09, LOW),
        (0.10, MODERATE),
        (0.24, MODERATE),
        (0.25, HIGH),
        (0.49, HIGH),
        (0.50, SEVERE),
        (1.00, SEVERE),
        (1.01, NO_TRAVEL),
    ],
)
def test_rain_thresholds(rain, expected):
    assert classify(rain=rain).level == expected


@pytest.mark.parametrize(
    ("snow", "expected"),
    [
        (0, LOW),
        (0.49, LOW),
        (0.5, MODERATE),
        (0.99, MODERATE),
        (1.0, HIGH),
        (1.99, HIGH),
        (2.0, SEVERE),
        (3.0, SEVERE),
        (3.01, NO_TRAVEL),
    ],
)
def test_snow_thresholds(snow, expected):
    assert classify(snow=snow).level == expected


@pytest.mark.parametrize(
    ("wind", "load", "expected"),
    [
        # >= 55 mph is No Travel for any load
        (55, 0, NO_TRAVEL),
        # 45–54 mph + > 30,000 lb -> No Travel
        (45, 30_000, SEVERE),
        (45, 30_001, NO_TRAVEL),
        (54.99, 30_001, NO_TRAVEL),
        # 35–44 mph + > 40,000 lb -> Severe
        (35, 40_000, HIGH),
        (35, 40_001, SEVERE),
        (44.99, 40_001, SEVERE),
        # Heavy loads do not change other wind bands
        (34.99, 80_000, MODERATE),
        (10, 80_000, LOW),
    ],
)
def test_load_rules(wind, load, expected):
    assert classify(wind=wind, load=load).level == expected


def test_worst_condition_sets_the_level():
    result = classify(wind=30, rain=0.30, snow=2.5)

    assert result.level == SEVERE
    assert result.drivers == ("snow",)


def test_all_variables_tied_at_the_worst_level_are_drivers():
    result = classify(wind=36, rain=0.30)

    assert result.level == HIGH
    assert result.drivers == ("wind", "rain")


def test_low_risk_has_no_drivers():
    result = classify(wind=10, rain=0.01)

    assert result.level == LOW
    assert result.drivers == ()
    assert result.load_adjusted is False


def test_load_adjusted_when_load_rule_raises_final_level():
    result = classify(wind=47, rain=0.12, load=35_000)

    assert result.level == NO_TRAVEL
    assert result.drivers == ("wind",)
    assert result.load_adjusted is True


def test_not_load_adjusted_when_another_variable_dominates():
    # The load rule raises wind to Severe, but snow is already No Travel.
    result = classify(wind=40, snow=3.5, load=45_000)

    assert result.level == NO_TRAVEL
    assert result.drivers == ("snow",)
    assert result.load_adjusted is False


@pytest.mark.parametrize(
    ("wind", "rain", "snow", "expected"),
    [
        (0, 0, 0, 0.0),
        (30, 0, 0, 1.5),  # halfway through Moderate wind (25–35)
        (0, 0.175, 0, 1.5),  # halfway through Moderate rain (0.10–0.25)
        (0, 0, 1.5, 2.5),  # halfway through High snow (1.0–2.0)
        (60, 0, 0, 4.0),
        (0, 0.75, 1.2, 3.5),  # the worst variable wins
    ],
)
def test_severity_score_interpolates_within_bands(wind, rain, snow, expected):
    assert severity_score(wind, rain, snow, load_weight_lb=0) == pytest.approx(expected)


def test_severity_score_applies_load_rules():
    assert severity_score(40, 0, 0, load_weight_lb=40_000) == pytest.approx(2.5)  # High
    assert severity_score(40, 0, 0, load_weight_lb=40_001) == pytest.approx(3.5)  # Severe
    assert severity_score(50, 0, 0, load_weight_lb=30_001) == 4.0  # No Travel


def test_severity_score_never_contradicts_the_risk_level():
    winds = [0, 24.99, 25, 30, 35, 44.99, 45, 50, 54.99, 55, 70]
    rains = [0, 0.1, 0.2, 0.25, 0.5, 1.0, 1.01]
    snows = [0, 0.5, 1.0, 2.0, 3.0, 3.01]
    loads = [0, 30_001, 40_001]
    for wind, rain, snow, load in itertools.product(winds, rains, snows, loads):
        level = classify_checkpoint(wind, rain, snow, load).level
        assert int(severity_score(wind, rain, snow, load)) == level, (wind, rain, snow, load)


def test_level_labels_match_api_contract():
    assert [level.label for level in RiskLevel] == ["low", "moderate", "high", "severe", "no_travel"]
