"""Weather risk classification for a single checkpoint.

Thresholds and load rules come straight from the assessment brief. Where the
brief's ranges touch (e.g. rain 0.10–0.25 and 0.25–0.50), the lower bound is
inclusive. Rain and snow only reach No Travel when strictly above the top
value (> 1.00 in/hr, > 3.0 in/hr), while wind reaches it at >= 55 mph.
"""

from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Band:
    level: RiskLevel
    min_value: float
    inclusive: bool = True


# Bands are ordered from worst to best; anything below the last one is Low.
WIND_GUST_BANDS_MPH = (
    Band(RiskLevel.NO_TRAVEL, 55),
    Band(RiskLevel.SEVERE, 45),
    Band(RiskLevel.HIGH, 35),
    Band(RiskLevel.MODERATE, 25),
)
RAIN_BANDS_IN_HR = (
    Band(RiskLevel.NO_TRAVEL, 1.00, inclusive=False),
    Band(RiskLevel.SEVERE, 0.50),
    Band(RiskLevel.HIGH, 0.25),
    Band(RiskLevel.MODERATE, 0.10),
)
SNOW_BANDS_IN_HR = (
    Band(RiskLevel.NO_TRAVEL, 3.0, inclusive=False),
    Band(RiskLevel.SEVERE, 2.0),
    Band(RiskLevel.HIGH, 1.0),
    Band(RiskLevel.MODERATE, 0.5),
)

# Load rules (wind >= 55 mph is already No Travel for any load via the bands).
NO_TRAVEL_LOAD_LB_IN_SEVERE_WIND = 30_000  # 45–54 mph + > 30,000 lb -> No Travel
SEVERE_LOAD_LB_IN_HIGH_WIND = 40_000  # 35–44 mph + > 40,000 lb -> Severe


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    drivers: tuple[str, ...]  # variables that set the level; empty when Low
    load_adjusted: bool  # True when a load rule raised the final level


def classify_checkpoint(
    wind_gust_mph: float,
    rain_in_hr: float,
    snow_in_hr: float,
    load_weight_lb: float,
) -> RiskAssessment:
    weather_wind_level = level_for(wind_gust_mph, WIND_GUST_BANDS_MPH)
    levels = {
        "wind": apply_load_rules(weather_wind_level, load_weight_lb),
        "rain": level_for(rain_in_hr, RAIN_BANDS_IN_HR),
        "snow": level_for(snow_in_hr, SNOW_BANDS_IN_HR),
    }
    level = max(levels.values())

    if level == RiskLevel.LOW:
        return RiskAssessment(RiskLevel.LOW, drivers=(), load_adjusted=False)

    drivers = tuple(name for name, value in levels.items() if value == level)
    load_adjusted = "wind" in drivers and levels["wind"] > weather_wind_level
    return RiskAssessment(level, drivers, load_adjusted)


def severity_score(
    wind_gust_mph: float,
    rain_in_hr: float,
    snow_in_hr: float,
    load_weight_lb: float,
) -> float:
    """Continuous 0–4 version of `classify_checkpoint`, used by the heatmap.

    The integer part is always the checkpoint's risk level; the fraction is
    how far the value is into its band, so colors blend smoothly without ever
    contradicting the discrete classification.
    """
    return max(
        _wind_score(wind_gust_mph, load_weight_lb),
        _band_score(rain_in_hr, RAIN_BANDS_IN_HR),
        _band_score(snow_in_hr, SNOW_BANDS_IN_HR),
    )


def level_for(value: float, bands: tuple[Band, ...]) -> RiskLevel:
    for band in bands:
        if value > band.min_value or (band.inclusive and value == band.min_value):
            return band.level
    return RiskLevel.LOW


def apply_load_rules(wind_level: RiskLevel, load_weight_lb: float) -> RiskLevel:
    if wind_level == RiskLevel.SEVERE and load_weight_lb > NO_TRAVEL_LOAD_LB_IN_SEVERE_WIND:
        return RiskLevel.NO_TRAVEL
    if wind_level == RiskLevel.HIGH and load_weight_lb > SEVERE_LOAD_LB_IN_HIGH_WIND:
        return RiskLevel.SEVERE
    return wind_level


# Keeps a value at the top of a band (e.g. rain = 1.00, still Severe) below the next level.
MAX_BAND_FRACTION = 0.999


def _band_score(value: float, bands: tuple[Band, ...]) -> float:
    level = level_for(value, bands)
    if level == RiskLevel.NO_TRAVEL:
        return float(RiskLevel.NO_TRAVEL)
    band_starts = {band.level: band.min_value for band in bands} | {RiskLevel.LOW: 0.0}
    start, end = band_starts[level], band_starts[RiskLevel(level + 1)]
    return level + min((value - start) / (end - start), MAX_BAND_FRACTION)


def _wind_score(wind_gust_mph: float, load_weight_lb: float) -> float:
    score = _band_score(wind_gust_mph, WIND_GUST_BANDS_MPH)
    weather_level = RiskLevel(int(score))
    adjusted = apply_load_rules(weather_level, load_weight_lb)
    if adjusted == weather_level:
        return score
    if adjusted == RiskLevel.NO_TRAVEL:
        return float(RiskLevel.NO_TRAVEL)
    return adjusted + (score - weather_level)
