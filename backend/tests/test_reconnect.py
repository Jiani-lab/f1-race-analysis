"""Tests for app._is_reconnect and SessionState.resume() -- the dedup fix
added 2026-08-04 so a stream stutter (buffering, a brief drop) does not
spawn a brand-new session_id for what is really the same broadcast.
"""

import time

import app


def test_no_prior_session_is_never_a_reconnect():
    assert app._is_reconnect(session_id=None, end_ms=None, now_ms=1_000_000) is False


def test_prior_session_still_active_end_ms_none_is_not_a_reconnect():
    # end_ms is only set by SessionState.end() -- a session that never
    # ended (still mid-race) should never be treated as "reconnecting".
    assert app._is_reconnect(session_id="race-1", end_ms=None, now_ms=1_000_000) is False


def test_ended_moments_ago_is_a_reconnect():
    now = 1_000_000_000
    ended = now - 60_000  # 1 minute ago
    assert app._is_reconnect(session_id="race-1", end_ms=ended, now_ms=now) is True


def test_ended_just_inside_the_gap_is_a_reconnect():
    now = 1_000_000_000
    ended = now - app.SESSION_RESUME_GAP_MS  # exactly at the boundary
    assert app._is_reconnect(session_id="race-1", end_ms=ended, now_ms=now) is True


def test_ended_just_outside_the_gap_is_not_a_reconnect():
    now = 1_000_000_000
    ended = now - app.SESSION_RESUME_GAP_MS - 1
    assert app._is_reconnect(session_id="race-1", end_ms=ended, now_ms=now) is False


def test_ended_a_long_time_ago_is_not_a_reconnect():
    now = 1_000_000_000
    ended = now - 3 * 60 * 60 * 1000  # 3 hours ago
    assert app._is_reconnect(session_id="race-1", end_ms=ended, now_ms=now) is False


def test_resume_keeps_the_same_session_id_and_start_ms():
    state = app.SessionState()
    state.start()
    original_id = state.session_id
    original_start = state.start_ms
    state.end()
    assert state.status == "ended"

    state.resume()
    assert state.status == "active"
    assert state.session_id == original_id  # not a new race
    assert state.start_ms == original_start  # not reset either
    assert state.end_ms is None


def test_start_always_creates_a_new_session_id():
    # session_id is a millisecond timestamp (f"race-{now_ms}") -- calling
    # start() truly back-to-back with no gap can collide on the same
    # millisecond (caught for real running this test: two calls executed
    # microseconds apart produced an identical id). Not a production bug:
    # _detection_loop only ever calls start() after a 90s poll sleep, never
    # back-to-back -- the tiny sleep here just reproduces that real gap
    # instead of an unrealistic zero-gap scenario nothing in the app does.
    state = app.SessionState()
    state.start()
    first_id = state.session_id
    state.end()
    time.sleep(0.002)
    state.start()
    second_id = state.session_id
    assert first_id != second_id
