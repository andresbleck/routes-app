"""Route risk summaries and recommendation ranking.

Routes are ranked lexicographically, following the brief's preference order:
fewest Severe miles, fewest High miles, lowest average risk, shortest travel
time. No Travel miles are compared first because No Travel is worse than
Severe and the brief does not place it. Values are rounded before comparing
so floating-point noise never decides between two routes.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from trips.domain.risk import RiskLevel


@dataclass(frozen=True)
class RouteSummary:
    route_id: str
    duration_seconds: float
    miles_by_level: dict[RiskLevel, float]
    average_risk: float  # distance-weighted mean of level scores (0–4)
    max_level: RiskLevel

    @property
    def has_no_travel(self) -> bool:
        return self.miles_by_level[RiskLevel.NO_TRAVEL] > 0


@dataclass(frozen=True)
class Criterion:
    name: str
    description: str
    value: Callable[[RouteSummary], float]
    unit: str


def _miles(level: RiskLevel) -> Callable[[RouteSummary], float]:
    return lambda summary: round(summary.miles_by_level[level], 1)


CRITERIA = (
    Criterion("no_travel_miles", "fewest No Travel miles", _miles(RiskLevel.NO_TRAVEL), "mi"),
    Criterion("severe_miles", "fewest Severe miles", _miles(RiskLevel.SEVERE), "mi"),
    Criterion("high_miles", "fewest High miles", _miles(RiskLevel.HIGH), "mi"),
    Criterion("average_risk", "lowest average risk", lambda s: round(s.average_risk, 2), ""),
    Criterion("travel_time", "shortest travel time", lambda s: round(s.duration_seconds / 60), "min"),
)


@dataclass(frozen=True)
class Ranking:
    routes: list[RouteSummary]  # best first
    decided_by: Criterion | None  # first criterion separating #1 from #2

    @property
    def recommended(self) -> RouteSummary:
        return self.routes[0]


def summarize_route(
    route_id: str,
    duration_seconds: float,
    segments: Iterable[tuple[float, RiskLevel]],
) -> RouteSummary:
    """Build a summary from (segment_miles, level) pairs, one per checkpoint."""
    miles_by_level = dict.fromkeys(RiskLevel, 0.0)
    for miles, level in segments:
        miles_by_level[level] += miles

    total_miles = sum(miles_by_level.values())
    weighted = sum(level * miles for level, miles in miles_by_level.items())
    return RouteSummary(
        route_id=route_id,
        duration_seconds=duration_seconds,
        miles_by_level=miles_by_level,
        average_risk=weighted / total_miles if total_miles else 0.0,
        max_level=max((level for level, miles in miles_by_level.items() if miles > 0), default=RiskLevel.LOW),
    )


def ranking_key(summary: RouteSummary) -> tuple[float, ...]:
    return tuple(criterion.value(summary) for criterion in CRITERIA)


def rank_routes(summaries: list[RouteSummary]) -> Ranking:
    # sorted() is stable, so full ties keep the provider's order.
    routes = sorted(summaries, key=ranking_key)
    decided_by = None
    if len(routes) > 1:
        decided_by = next(
            (c for c in CRITERIA if c.value(routes[0]) != c.value(routes[1])),
            None,
        )
    return Ranking(routes, decided_by)


def explain(ranking: Ranking) -> str:
    if len(ranking.routes) == 1:
        return "Only one route is available."
    criterion = ranking.decided_by
    if criterion is None:
        return "All routes tie on every criterion; the first route returned by the provider is recommended."
    best = _format(criterion.value(ranking.routes[0]), criterion.unit)
    runner_up = _format(criterion.value(ranking.routes[1]), criterion.unit)
    return f"Recommended for {criterion.description} ({best} vs {runner_up})."


def _format(value: float, unit: str) -> str:
    return f"{value:g} {unit}".strip()
