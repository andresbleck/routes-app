import pytest

from trips.domain.ranking import explain, rank_routes, summarize_route
from trips.domain.risk import RiskLevel

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = RiskLevel
HOUR = 3600


def route(route_id, segments, hours=10):
    return summarize_route(route_id, hours * HOUR, segments)


def ranked_ids(*summaries):
    return [summary.route_id for summary in rank_routes(list(summaries)).routes]


# --- summarize_route -------------------------------------------------------


def test_summary_adds_miles_per_level():
    summary = route("a", [(10, LOW), (25, HIGH), (15, LOW), (5, SEVERE)])

    assert summary.miles_by_level == {LOW: 25, MODERATE: 0, HIGH: 25, SEVERE: 5, NO_TRAVEL: 0}
    assert summary.max_level == SEVERE
    assert summary.has_no_travel is False


def test_average_risk_is_weighted_by_miles():
    # (90 mi * 0 + 10 mi * 4) / 100 mi
    summary = route("a", [(90, LOW), (10, NO_TRAVEL)])

    assert summary.average_risk == pytest.approx(0.4)
    assert summary.has_no_travel is True


def test_empty_route_summary_is_low_risk():
    summary = route("a", [])

    assert summary.average_risk == 0
    assert summary.max_level == LOW


# --- rank_routes: preference order -----------------------------------------


def test_fewest_severe_miles_wins_first():
    safer = route("safer", [(20, HIGH), (80, LOW)], hours=12)
    faster = route("faster", [(5, SEVERE), (95, LOW)], hours=8)

    ranking = rank_routes([faster, safer])

    assert [r.route_id for r in ranking.routes] == ["safer", "faster"]
    assert ranking.decided_by.name == "severe_miles"


def test_fewest_high_miles_breaks_severe_tie():
    a = route("a", [(5, SEVERE), (30, HIGH), (65, LOW)])
    b = route("b", [(5, SEVERE), (10, HIGH), (85, LOW)])

    ranking = rank_routes([a, b])

    assert ranking.recommended.route_id == "b"
    assert ranking.decided_by.name == "high_miles"


def test_lowest_average_risk_breaks_high_tie():
    a = route("a", [(10, HIGH), (60, MODERATE), (30, LOW)])
    b = route("b", [(10, HIGH), (20, MODERATE), (70, LOW)])

    ranking = rank_routes([a, b])

    assert ranking.recommended.route_id == "b"
    assert ranking.decided_by.name == "average_risk"


def test_shortest_travel_time_breaks_risk_tie():
    slow = route("slow", [(100, LOW)], hours=11)
    fast = route("fast", [(100, LOW)], hours=9)

    ranking = rank_routes([slow, fast])

    assert ranking.recommended.route_id == "fast"
    assert ranking.decided_by.name == "travel_time"


def test_no_travel_miles_rank_before_severe_miles():
    blocked = route("blocked", [(10, NO_TRAVEL), (90, LOW)])
    severe = route("severe", [(11, SEVERE), (89, LOW)])

    ranking = rank_routes([blocked, severe])

    assert ranking.recommended.route_id == "severe"
    assert ranking.decided_by.name == "no_travel_miles"


def test_full_ranking_of_three_routes():
    a = route("a", [(10, HIGH), (90, LOW)], hours=9)
    b = route("b", [(100, LOW)], hours=12)
    c = route("c", [(10, HIGH), (90, LOW)], hours=8)

    assert ranked_ids(a, b, c) == ["b", "c", "a"]


# --- rank_routes: ties and edge cases --------------------------------------


def test_rounding_noise_does_not_decide():
    # 10.04 and 10.01 Severe miles both round to 10.0, so High miles decide.
    a = route("a", [(10.04, SEVERE), (20, HIGH)])
    b = route("b", [(10.01, SEVERE), (30, HIGH)])

    ranking = rank_routes([b, a])

    assert ranking.recommended.route_id == "a"
    assert ranking.decided_by.name == "high_miles"


def test_full_tie_keeps_provider_order():
    first = route("first", [(100, LOW)])
    second = route("second", [(100, LOW)])

    ranking = rank_routes([first, second])

    assert ranking.recommended.route_id == "first"
    assert ranking.decided_by is None


def test_single_route_is_recommended():
    ranking = rank_routes([route("only", [(100, MODERATE)])])

    assert ranking.recommended.route_id == "only"
    assert ranking.decided_by is None


# --- explain ---------------------------------------------------------------


def test_explanation_names_deciding_criterion_and_values():
    a = route("a", [(12.5, HIGH), (87.5, LOW)])
    b = route("b", [(37.5, HIGH), (62.5, LOW)])

    assert explain(rank_routes([a, b])) == "Recommended for fewest High miles (12.5 mi vs 37.5 mi)."


def test_explanation_for_travel_time():
    a = route("a", [(100, LOW)], hours=9)
    b = route("b", [(100, LOW)], hours=10)

    assert explain(rank_routes([a, b])) == "Recommended for shortest travel time (540 min vs 600 min)."


def test_explanation_for_tie_and_single_route():
    tie = rank_routes([route("a", [(100, LOW)]), route("b", [(100, LOW)])])
    single = rank_routes([route("a", [(100, LOW)])])

    assert "tie" in explain(tie)
    assert explain(single) == "Only one route is available."
