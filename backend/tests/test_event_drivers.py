"""Tests for analysis._resolve_event_drivers -- the driver-tagging fix
added 2026-08-04. Real bug this exists to catch a regression of: a live
race-control event ("Race Control logs a Hamilton incident for moving
before the signal on lap 6") was tagged drivers: [] end to end, so it
could never trigger a push notification for a Hamilton-favoriting viewer
even though the evidence text named him directly -- see
test_llm_reading_fills_gap_when_raw_extraction_is_empty below, which is
that exact real case.
"""

import analysis


def test_raw_drivers_wins_when_present():
    # detect_pit_stop-style extraction already pulled a code from
    # structured OCR -- more reliable than an LLM re-reading the same
    # evidence text, so it should never be second-guessed even if the LLM
    # (wrongly, or just differently) suggests something else.
    result = analysis._resolve_event_drivers(["ALB"], ["HAM"])
    assert result == ["ALB"]


def test_llm_reading_fills_gap_when_raw_extraction_is_empty():
    # The real case: detect_race_control_banners always ships drivers: []
    # by design (regex should not guess), so the LLM's own reading of the
    # evidence text is the only source -- and it must actually be used,
    # not discarded.
    result = analysis._resolve_event_drivers([], ["HAM"])
    assert result == ["HAM"]


def test_llm_reading_deduplicated_and_sorted():
    result = analysis._resolve_event_drivers([], ["HAM", "VER", "HAM"])
    assert result == ["HAM", "VER"]


def test_invalid_driver_codes_from_llm_are_dropped_not_trusted():
    # Never trust a free-form model output into a field other code treats
    # as validated -- "XXX" is not a real 2026 grid code.
    result = analysis._resolve_event_drivers([], ["HAM", "XXX"])
    assert result == ["HAM"]


def test_llm_codes_are_case_normalized():
    result = analysis._resolve_event_drivers([], ["ham"])
    assert result == ["HAM"]


def test_llm_drivers_wrong_type_degrades_to_empty_not_a_crash():
    # Defensive against a malformed/unexpected LLM response shape (a
    # string instead of a list, for example) -- same "never trust the
    # model blindly" posture as the rest of _parse_event_batch_json.
    result = analysis._resolve_event_drivers([], "HAM")
    assert result == []


def test_both_empty_is_empty():
    assert analysis._resolve_event_drivers([], []) == []
