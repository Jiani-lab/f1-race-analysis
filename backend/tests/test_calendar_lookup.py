"""Tests for app._lookup_calendar_gp -- the date-based auto-naming fallback
added 2026-08-04 so a freshly-detected session gets a real Grand Prix name
instead of staying a generic "F1 LIVE SESSION -- <date>" placeholder
forever. Real regression coverage: the first version used a 1-day slack
window and failed to match the one real session already on record (see
test_hungarian_gp_matches_with_real_capture_date below) -- these tests
exist so that specific mistake cannot silently come back.
"""

import time

import app


def _ms(date_str: str, hour: int = 12) -> int:
    """Local-time midday timestamp for a YYYY-MM-DD date -- midday avoids
    any timezone-boundary edge case a midnight timestamp could hit."""
    return int(time.mktime(time.strptime(f"{date_str} {hour}:00:00", "%Y-%m-%d %H:%M:%S")) * 1000)


def test_none_start_ms_returns_none():
    assert app._lookup_calendar_gp(None) is None


def test_hungarian_gp_matches_with_real_capture_date():
    # The regression case: race-1785212472206's actual manually-recorded
    # capture date is 2026-07-28, but the researched official weekend is
    # 2026-07-24 to 07-26. A 1-day slack window (the first version shipped)
    # does not cover this real 2-day drift; 3 days does.
    result = app._lookup_calendar_gp(_ms("2026-07-28"))
    assert result is not None
    assert result["name"] == "FORMULA 1 HUNGARIAN GRAND PRIX"
    assert result["round"] == "ROUND 13 / 2026"


def test_exact_official_weekend_date_matches():
    result = app._lookup_calendar_gp(_ms("2026-07-04"))  # British GP weekend
    assert result == {"name": "FORMULA 1 BRITISH GRAND PRIX", "round": "ROUND 11 / 2026"}


def test_gap_between_races_does_not_false_match():
    # 2026-08-10 sits well inside the real gap between the Dutch GP
    # (Aug 21-23) and the Hungarian GP weekend+slack (through ~Jul 29) --
    # nothing should match here. A regression that widened slack too far
    # would start bridging adjacent races together.
    assert app._lookup_calendar_gp(_ms("2026-08-10")) is None


def test_slack_boundary_just_inside_matches():
    # Dutch GP weekend is 2026-08-21 to 2026-08-23; slack is 3 days, so
    # 2026-08-24 (1 day past the end date) should still match.
    result = app._lookup_calendar_gp(_ms("2026-08-24"))
    assert result is not None
    assert "DUTCH" in result["name"]


def test_slack_boundary_just_outside_does_not_match():
    # 5 days past the Dutch GP's end date is outside the 3-day slack.
    assert app._lookup_calendar_gp(_ms("2026-08-28")) is None


def test_known_limitation_close_races_can_have_overlapping_slack_windows():
    # Belgian GP (Jul 17-19) and Hungarian GP (Jul 24-26) are only 4 real
    # days apart -- with 3-day slack on each side (6 days combined) their
    # windows genuinely overlap on Jul 21-22. This is NOT a bug to silently
    # "fix" by shrinking slack (that broke the real Hungarian-GP capture-
    # date case above) -- it is a real, narrow tradeoff of the current
    # 3-day window. Documented here as the actual observed behavior (first
    # matching calendar entry wins, deterministic, never crashes or
    # returns something not on the calendar) rather than left unverified.
    result = app._lookup_calendar_gp(_ms("2026-07-22"))
    assert result is not None
    assert result["name"] in ("FORMULA 1 BELGIAN GRAND PRIX", "FORMULA 1 HUNGARIAN GRAND PRIX")
