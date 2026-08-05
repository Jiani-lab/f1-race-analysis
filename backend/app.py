"""F1 dual-stream analysis -- local FastAPI app.

Run with (from project root):
  uv run uvicorn app:app --app-dir backend --reload --port 8800
(--app-dir puts backend/ on sys.path so the plain `import analysis` /
`import retrieval` below resolve, without needing package __init__.py)

Includes its own background polling loop for live-stream detection --
deliberately not openclaw, not a Claude Code cloud Routine (can't reach
localhost Luci anyway). Just an asyncio task in this same process.
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import analysis
import push
import rag
import retrieval
from detect import is_f1_live_now

POLL_INTERVAL_SEC = 90
# How long after a session ends a fresh detection still counts as "the same
# broadcast reconnecting" rather than a new race -- generous enough to
# cover a real stream stall/buffer/ad-break (several missed poll ticks),
# short enough that two genuinely distinct sessions hours apart (Saturday
# quali, Sunday race) are never merged.
SESSION_RESUME_GAP_MS = 15 * 60 * 1000
FRONTEND_HOME = Path(__file__).parent.parent / "frontend" / "home.html"
FRONTEND_SETTINGS = Path(__file__).parent.parent / "frontend" / "settings.html"
FRONTEND_CHAT = Path(__file__).parent.parent / "frontend" / "chat.html"
FRONTEND_SW = Path(__file__).parent.parent / "frontend" / "sw.js"
FRONTEND_ICON = Path(__file__).parent.parent / "frontend" / "icon.png"

# Same restraint rules as the Phase 3 in-page badge's pollForNotifications()
# (frontend/index.html) -- moved server-side because a real push must be
# sent by the backend itself, which has no visibility into a browser's
# localStorage. Not a redesign, just the same two numbers relocated.
NOTIF_COOLDOWN_MS = 8 * 60 * 1000
NOTIF_MAX_PER_RACE = 6

# Real Grand Prix name/round for sessions captured before this per-session
# display metadata existed, or wherever the calendar auto-match below gets
# something wrong (sponsor-prefixed official names in particular -- the
# calendar only knows the plain country name, not "AWS Hungarian Grand
# Prix"). Checked first, before the calendar lookup, so a manual entry
# always wins.
SESSION_DISPLAY_NAMES = {
    "race-1785212472206": {"name": "FORMULA 1 AWS HUNGARIAN GRAND PRIX", "round": "ROUND 11 / 2026"},
}

# 2026 F1 calendar (race-weekend date range, country/host name, round number)
# -- used to auto-name a freshly-detected session instead of leaving it as
# the generic "F1 LIVE SESSION -- <date>" placeholder until someone manually
# adds it to SESSION_DISPLAY_NAMES above. Matched by date, not hardcoded per
# session_id, so every future auto-detected race gets a real name for free.
F1_2026_CALENDAR = [
    ("2026-03-06", "2026-03-08", "AUSTRALIAN"),
    ("2026-03-13", "2026-03-15", "CHINESE"),
    ("2026-03-27", "2026-03-29", "JAPANESE"),
    ("2026-04-10", "2026-04-12", "BAHRAIN"),
    ("2026-04-17", "2026-04-19", "SAUDI ARABIAN"),
    ("2026-05-01", "2026-05-03", "MIAMI"),
    ("2026-05-22", "2026-05-24", "CANADIAN"),
    ("2026-06-05", "2026-06-07", "MONACO"),
    ("2026-06-12", "2026-06-14", "SPANISH"),
    ("2026-06-26", "2026-06-28", "AUSTRIAN"),
    ("2026-07-03", "2026-07-05", "BRITISH"),
    ("2026-07-17", "2026-07-19", "BELGIAN"),
    ("2026-07-24", "2026-07-26", "HUNGARIAN"),
    ("2026-08-21", "2026-08-23", "DUTCH"),
    ("2026-09-04", "2026-09-06", "ITALIAN"),
    ("2026-09-11", "2026-09-13", "MADRID"),
    ("2026-09-24", "2026-09-26", "AZERBAIJAN"),
    ("2026-10-09", "2026-10-11", "SINGAPORE"),
    ("2026-10-23", "2026-10-25", "UNITED STATES"),
    ("2026-10-30", "2026-11-01", "MEXICO CITY"),
    ("2026-11-06", "2026-11-08", "SAO PAULO"),
    ("2026-11-19", "2026-11-21", "LAS VEGAS"),
    ("2026-11-27", "2026-11-29", "QATAR"),
    ("2026-12-04", "2026-12-06", "ABU DHABI"),
]
# Real broadcast coverage often starts a bit before/after the official
# weekend window (pre-race build-up shows, delayed replays, source
# calendars disagreeing by a day or two) -- checked against the one real
# session already on record (the manually-named Hungarian GP: captured
# 2026-07-28, researched calendar says weekend of 2026-07-24 to 07-26) --
# a 1-day buffer wasn't enough to cover that real drift, 3 days is.
_CALENDAR_SLACK_DAYS = 3


def _lookup_calendar_gp(start_ms: int | None) -> dict | None:
    if start_ms is None:
        return None
    day = time.strftime("%Y-%m-%d", time.localtime(start_ms / 1000))
    for round_num, (start_date, end_date, host) in enumerate(F1_2026_CALENDAR, start=1):
        lo = time.strftime("%Y-%m-%d", time.localtime(
            time.mktime(time.strptime(start_date, "%Y-%m-%d")) - _CALENDAR_SLACK_DAYS * 86400
        ))
        hi = time.strftime("%Y-%m-%d", time.localtime(
            time.mktime(time.strptime(end_date, "%Y-%m-%d")) + _CALENDAR_SLACK_DAYS * 86400
        ))
        if lo <= day <= hi:
            return {"name": f"FORMULA 1 {host} GRAND PRIX", "round": f"ROUND {round_num} / 2026"}
    return None
# Coarser than the 90s live-detection tick on purpose: event phrasing shells
# out to `claude -p` (real wall-clock cost per event, ~15-90s each measured
# against real events), whereas detection is a cheap Luci query. A separate
# interval keeps tuning one independent of the other. Event-level caching
# (analysis.get_phrased_events) means most ticks are cheap no-ops once a
# session's events have mostly stabilized -- only genuinely new events cost
# real time.
EVENT_REFRESH_INTERVAL_SEC = 300
FRONTEND_INDEX = Path(__file__).parent.parent / "frontend" / "index.html"


class SessionState:
    def __init__(self):
        self.status = "idle"  # idle | active | ended
        self.session_id: str | None = None
        self.start_ms: int | None = None
        self.end_ms: int | None = None

    def start(self):
        now = int(time.time() * 1000)
        self.status = "active"
        self.session_id = f"race-{now}"
        self.start_ms = now
        self.end_ms = None

    def resume(self):
        """Reactivates the existing session_id in place of start() -- for
        when detection drops out briefly (stream buffering, a stall long
        enough to miss one 90s poll tick) and picks back up moments later.
        Keeps session_id/start_ms unchanged so it is genuinely a
        continuation: the same merged.jsonl keeps being appended to, and
        push.py's per-session notif_state (cooldown/count) isn't reset,
        so a flaky reconnect can't grant extra notification budget for
        what is really one race."""
        self.status = "active"
        self.end_ms = None

    def end(self):
        self.status = "ended"
        self.end_ms = int(time.time() * 1000)

    def as_dict(self):
        return {
            "status": self.status,
            "session_id": self.session_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
        }


state = SessionState()


def _resume_last_session() -> None:
    """On process start, reattach to the most recently written session on
    disk instead of coming up idle -- otherwise every server restart (e.g.
    to pick up a backend code change) silently orphans whatever session the
    frontend was already pointed at. Marked "ended": if a restart happens
    while a stream is genuinely still live, the next detection-loop tick
    will notice and start a fresh session anyway."""
    if not retrieval.SESSIONS_DIR.exists():
        return
    candidates = sorted(
        (d for d in retrieval.SESSIONS_DIR.iterdir() if (d / "merged.jsonl").exists()),
        key=lambda d: (d / "merged.jsonl").stat().st_mtime,
    )
    if not candidates:
        return
    session_dir = candidates[-1]
    records = analysis._load_log(session_dir.name)  # noqa: SLF001 -- internal reuse within backend
    if not records:
        return
    state.status = "ended"
    state.session_id = session_dir.name
    state.start_ms = records[0]["timestamp"]
    state.end_ms = records[-1]["timestamp"]
    print(f"[watcher] resumed last session {state.session_id} on startup")


_resume_last_session()


def _is_reconnect(session_id: str | None, end_ms: int | None, now_ms: int) -> bool:
    """A stream that stutters (buffering, a brief drop) can miss one or two
    90s poll ticks and read as "not active" for a few minutes before
    reconnecting -- without this check that would start() a brand-new
    session_id for what's really the same broadcast, duplicating it on the
    homepage, resetting the push notification cooldown/count for what
    should still be one race's budget, and firing a second "New F1 session
    detected" push moments after the first. Only a genuine same-race
    reconnect qualifies: same session_id already on record and it ended
    recently enough that a new broadcast starting from scratch is
    implausible. Pure function (no clock/global-state reads) on purpose --
    see backend/tests/test_reconnect.py."""
    return (
        session_id is not None
        and end_ms is not None
        and (now_ms - end_ms) <= SESSION_RESUME_GAP_MS
    )


async def _detection_loop():
    while True:
        try:
            if state.status != "active" and is_f1_live_now():
                if _is_reconnect(state.session_id, state.end_ms, int(time.time() * 1000)):
                    state.resume()
                    print(f"[watcher] F1 stream re-detected within {SESSION_RESUME_GAP_MS // 1000}s of the last "
                          f"one ending -- treating as a reconnect, resuming session {state.session_id} "
                          f"(no duplicate session, no duplicate push)")
                else:
                    state.start()
                    print(f"[watcher] F1 stream detected, started session {state.session_id}")
                    info = _display_info(state.session_id, state.start_ms, None, "active")
                    if push.get_preferences()["notify_session_start"]:
                        push.send_push(
                            "New F1 session detected",
                            f"{info['name']} is on screen now.",
                            f"/race?session={state.session_id}",
                        )
        except Exception as e:  # noqa: BLE001 -- keep the loop alive no matter what
            print(f"[watcher] detection error (will retry): {e}")
        await asyncio.sleep(POLL_INTERVAL_SEC)


def _generate_events(session_id: str, from_ms: int, to_ms: int) -> list[dict]:
    """Shared by the /session/events endpoint (synchronous, first-load-pays
    the cost per the user's explicit choice) and the background refresh
    loop below. retrieval.refresh_session already recomputes raw_events.json
    as part of its normal merge step -- this just also runs the phrasing
    pass, which is separately cached (analysis.get_phrased_events), so
    repeat calls after the first are cheap no-ops for already-seen events."""
    if _is_live(session_id):
        retrieval.refresh_session(session_id, from_ms, to_ms)
    raw_path = retrieval.SESSIONS_DIR / session_id / "raw_events.json"
    raw_events = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else []
    return analysis.get_phrased_events(session_id, raw_events)


def _maybe_push_notification(session_id: str, events: list[dict]) -> None:
    """Server-side mirror of frontend/index.html's pollForNotifications() --
    same two restraint layers (8-min cooldown, 6/race hard cap, highest-
    importance-only when several qualify at once), just relocated here
    because a real push has to be sent by the backend, which can't read a
    browser's localStorage. Silently no-ops if no one has ever completed
    the one-time subscribe flow (push.send_push returns False for that)."""
    prefs = push.get_preferences()
    favorite = prefs["favorite_driver"]
    if not favorite or not prefs["notify_driver_events"]:
        return
    notif_state = push.get_notif_state(session_id)
    if notif_state["count"] >= NOTIF_MAX_PER_RACE:
        return
    if time.time() * 1000 - notif_state["last_fired_ms"] < NOTIF_COOLDOWN_MS:
        return
    seen = set(notif_state["seen_keys"])
    candidates = [
        e for e in events
        if e.get("notification_worthy") and e.get("notification_hook")
        and favorite in (e.get("drivers") or [])
        and analysis._event_key(e) not in seen  # noqa: SLF001 -- internal reuse within backend
    ]
    if not candidates:
        return
    chosen = max(candidates, key=lambda e: e["importance"])
    sent = push.send_push(
        f"Lap {chosen['lap']} — {favorite}",
        chosen["notification_hook"],
        f"/race?session={session_id}",
    )
    if not sent:
        return
    seen.add(analysis._event_key(chosen))  # noqa: SLF001 -- internal reuse within backend
    push.save_notif_state(session_id, {
        "count": notif_state["count"] + 1,
        "last_fired_ms": time.time() * 1000,
        "seen_keys": list(seen),
    })


async def _event_refresh_loop():
    """Separate from _detection_loop on purpose (see EVENT_REFRESH_INTERVAL_SEC)
    -- runs the sync refresh+phrase work in a thread so it doesn't block the
    FastAPI event loop (and thus doesn't block the live-detection loop or
    any concurrently-handled request either) while it's shelling out to
    `claude -p`. The _CLAUDE_LOCK inside analysis._run_claude means this
    naturally waits its turn behind any user-triggered analysis call
    in-flight at the same moment, rather than racing it."""
    while True:
        try:
            if state.status == "active" and state.session_id:
                from_ms, to_ms = _current_window(state.session_id)
                events = await asyncio.to_thread(_generate_events, state.session_id, from_ms, to_ms)
                _maybe_push_notification(state.session_id, events)
                records = analysis._load_log(state.session_id)  # noqa: SLF001 -- internal reuse within backend
                await asyncio.to_thread(rag.index_new_content, state.session_id, events, records)
        except Exception as e:  # noqa: BLE001 -- keep the loop alive no matter what
            print(f"[events] refresh error (will retry): {e}")
        await asyncio.sleep(EVENT_REFRESH_INTERVAL_SEC)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [asyncio.create_task(_detection_loop()), asyncio.create_task(_event_refresh_loop())]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="F1 Race Analysis", lifespan=lifespan)
app.mount("/img", StaticFiles(directory=Path(__file__).parent.parent / "frontend" / "img"), name="img")


def _session_exists(session_id: str) -> bool:
    return (retrieval.SESSIONS_DIR / session_id / "merged.jsonl").exists()


def _is_live(session_id: str) -> bool:
    """Real bug this fixes: refresh_session() unconditionally rewrites
    merged.jsonl (and strategy_trend.json etc) every time it's called, even
    for a race that ended hours ago and has nothing new to pull from Luci --
    that rewrite bumps the file's mtime on every single click, which quietly
    defeated analysis.py's mtime-keyed answer cache (every "identical"
    summary/catchup call looked "fresh" and re-ran `claude -p` anyway).
    Gating the refresh to only the currently-live session fixes both: no
    pointless re-fetch of already-complete data, and the cache actually
    holds for ended races."""
    return session_id == state.session_id and state.status == "active"


def _require_session(session_id: str | None = None) -> str:
    """Explicit session_id (from the dashboard's ?session= param, forwarded
    as a query param on every API call) always wins when given, so each
    race's dashboard tab stays pinned to its own data -- otherwise this falls
    back to the single live/most-recent session, same as before this
    multi-race support existed (today's live-detection flow for a brand new
    race still works with no session_id passed at all)."""
    if session_id:
        if session_id == state.session_id or _session_exists(session_id):
            return session_id
        raise HTTPException(404, f"No session found with id {session_id!r}")
    if not state.session_id:
        raise HTTPException(400, "No active or ended session yet -- start recording or wait for a live stream to be detected")
    return state.session_id


def _current_window(session_id: str) -> tuple[int, int]:
    """start/end for the window to (re-)ingest. Only the live global session
    has a meaningful "now" as its end -- a past race being browsed via
    ?session= is always fully ingested already and just needs its own
    recorded start/end, not the live clock."""
    if session_id == state.session_id:
        return state.start_ms, (state.end_ms or int(time.time() * 1000))
    records = analysis._load_log(session_id)  # noqa: SLF001 -- internal reuse within backend
    if not records:
        return 0, int(time.time() * 1000)
    return records[0]["timestamp"], records[-1]["timestamp"]


def _display_info(session_id: str, start_ms: int | None, end_ms: int | None, status: str) -> dict:
    known = SESSION_DISPLAY_NAMES.get(session_id) or _lookup_calendar_gp(start_ms) or {}
    date_str = time.strftime("%Y-%m-%d", time.localtime(start_ms / 1000)) if start_ms else "unknown date"
    return {
        "session_id": session_id,
        "name": known.get("name", f"F1 LIVE SESSION — {date_str}"),
        "round": known.get("round", date_str.upper()),
        "status": status,
        "start_ms": start_ms,
        "end_ms": end_ms,
    }


@app.get("/")
def home():
    return FileResponse(FRONTEND_HOME)


@app.get("/race")
def race_dashboard():
    return FileResponse(FRONTEND_INDEX)


@app.get("/settings")
def settings_page():
    return FileResponse(FRONTEND_SETTINGS)


@app.get("/chat")
def chat_page():
    return FileResponse(FRONTEND_CHAT)


@app.get("/sw.js")
def service_worker():
    # Must be served from the origin root -- a Service Worker's scope is the
    # directory it's served from, and root is the only scope that covers
    # both "/" (home.html) and "/race" (index.html).
    return FileResponse(FRONTEND_SW, media_type="application/javascript")


@app.get("/icon.png")
def notification_icon():
    return FileResponse(FRONTEND_ICON, media_type="image/png")


class PushSubscribeRequest(BaseModel):
    subscription: dict
    favorite_driver: str


@app.get("/push/vapid-public-key")
def push_vapid_public_key():
    return {"key": push.VAPID_PUBLIC_KEY_B64}


@app.post("/push/subscribe")
def push_subscribe(body: PushSubscribeRequest):
    push.save_subscription(body.subscription, body.favorite_driver)
    return {"ok": True}


@app.get("/push/preferences")
def push_preferences():
    """Backs the settings page's initial render -- the homepage's push-card
    never had to read this back (it trusts its own localStorage instead),
    but a dedicated settings page needs the server's actual saved state,
    since that's the only copy that's consistent across browsers/devices."""
    return push.get_preferences()


class PushPreferencesRequest(BaseModel):
    notify_session_start: bool
    notify_driver_events: bool
    favorite_driver: str | None = None


@app.post("/push/preferences")
def push_update_preferences(body: PushPreferencesRequest):
    push.save_preferences(body.notify_session_start, body.notify_driver_events, body.favorite_driver)
    return {"ok": True}


@app.post("/push/unsubscribe")
def push_unsubscribe():
    """'Forget this device' -- the browser-side PushSubscription.unsubscribe()
    call happens in the frontend (only the browser can invalidate its own
    subscription); this just drops our copy so send_push stops finding
    anything to send to, same as if it had never been set up."""
    push.clear_subscription()
    return {"ok": True}


@app.get("/sessions")
def list_sessions():
    """Backs the homepage's race picker. Only race-* dirs (excludes ad-hoc
    test fixtures like test-milestone0, which have no race_meta.json/full
    pipeline output and aren't real dashboards)."""
    out = {}
    if retrieval.SESSIONS_DIR.exists():
        for d in retrieval.SESSIONS_DIR.iterdir():
            if not d.name.startswith("race-") or not (d / "merged.jsonl").exists():
                continue
            records = analysis._load_log(d.name)  # noqa: SLF001 -- internal reuse within backend
            if not records:
                continue
            is_live = d.name == state.session_id
            status = state.status if is_live else "ended"
            out[d.name] = _display_info(d.name, records[0]["timestamp"], records[-1]["timestamp"], status)
    if state.session_id and state.session_id not in out:
        # Brand new live session: detected but hasn't written merged.jsonl
        # yet (first refresh_session call can lag up to EVENT_REFRESH_INTERVAL_SEC
        # behind detection). Surface it anyway so "watching a new race today"
        # shows up on the homepage immediately instead of after a delay.
        out[state.session_id] = _display_info(state.session_id, state.start_ms, state.end_ms, state.status)
    sessions = sorted(out.values(), key=lambda s: s["start_ms"] or 0, reverse=True)
    return {"sessions": sessions}


@app.get("/session/info")
def session_info(session_id: str | None = None):
    resolved = _require_session(session_id)
    is_live = resolved == state.session_id
    if is_live:
        return _display_info(resolved, state.start_ms, state.end_ms, state.status)
    records = analysis._load_log(resolved)  # noqa: SLF001 -- internal reuse within backend
    start_ms = records[0]["timestamp"] if records else None
    end_ms = records[-1]["timestamp"] if records else None
    return _display_info(resolved, start_ms, end_ms, "ended")


@app.get("/session/interest-options")
def session_interest_options(session_id: str | None = None):
    """Backs the onboarding modal's second question. Reuses session_info's
    display-name resolution (SESSION_DISPLAY_NAMES or a generic fallback) as
    the race identity passed into the web-search prompt -- cached forever
    per session_id on the analysis.py side, so this is a slow ~90s call at
    most once per race, not per visitor."""
    resolved = _require_session(session_id)
    info = session_info(resolved)
    return {"options": analysis.interest_options(resolved, info["name"])}


@app.get("/session/status")
def session_status():
    return state.as_dict()


@app.post("/session/end")
def session_end():
    session_id = _require_session()
    state.end()
    from_ms, to_ms = _current_window(session_id)
    retrieval.refresh_session(session_id, from_ms, to_ms)
    return state.as_dict()


@app.get("/session/catchup")
def session_catchup(since: int | None = None, session_id: str | None = None):
    resolved = _require_session(session_id)
    from_ms, to_ms = _current_window(resolved)
    if _is_live(resolved):
        retrieval.refresh_session(resolved, from_ms, to_ms)
    since_ms = since if since is not None else from_ms
    return {"text": analysis.catchup(resolved, since_ms)}


@app.get("/session/summary")
def session_summary(session_id: str | None = None):
    resolved = _require_session(session_id)
    from_ms, to_ms = _current_window(resolved)
    if _is_live(resolved):
        retrieval.refresh_session(resolved, from_ms, to_ms)
    return {"text": analysis.summary(resolved)}


class WhatIfRequest(BaseModel):
    hypothesis: str


@app.post("/session/whatif")
def session_whatif(body: WhatIfRequest, session_id: str | None = None):
    resolved = _require_session(session_id)
    return analysis.whatif(resolved, body.hypothesis)  # {text, verdict, scenarios}


@app.get("/session/timeline")
def session_timeline(session_id: str | None = None):
    resolved = _require_session(session_id)
    records = analysis._load_log(resolved)  # noqa: SLF001 -- internal reuse within backend
    events = [r for r in records if r["stream"] == "audio"]
    return {"events": events}


@app.get("/session/rule-lookup")
def session_rule_lookup(around: int, session_id: str | None = None):
    resolved = _require_session(session_id)
    return {"text": analysis.rule_lookup(resolved, around)}


@app.get("/session/strategy-trend")
def session_strategy_trend(session_id: str | None = None):
    resolved = _require_session(session_id)
    return {"points": analysis.strategy_trend(resolved)}


@app.get("/session/replay-cutoffs")
def session_replay_cutoffs(session_id: str | None = None):
    resolved = _require_session(session_id)
    return {"cutoffs": analysis.replay_cutoffs(resolved)}


@app.get("/session/race-meta")
def session_race_meta(session_id: str | None = None):
    resolved = _require_session(session_id)
    return analysis.race_meta(resolved)


@app.get("/session/retirements")
def session_retirements(session_id: str | None = None):
    resolved = _require_session(session_id)
    return {"retirements": analysis.retirements(resolved)}


@app.get("/session/events")
def session_events(session_id: str | None = None):
    """Unlike race-meta/retirements (pure readers), this one CAN trigger
    real work synchronously on first call for a session with no phrased
    events yet -- explicit user choice: "open and it generates live (maybe
    1-2 min)" over "show nothing until the next background tick." Already-
    phrased events are cached, so repeat calls (or later ones after the
    background loop has caught up) are fast."""
    resolved = _require_session(session_id)
    from_ms, to_ms = _current_window(resolved)
    events = _generate_events(resolved, from_ms, to_ms)
    return {"events": events}


class ChatRequest(BaseModel):
    question: str
    max_lap: int | None = None  # omitted by the standalone chat page; sent by the race-page widget


@app.post("/session/chat")
def session_chat(body: ChatRequest, session_id: str | None = None):
    """RAG Q&A over whatever's been indexed for this session so far (see
    rag.py) -- can lag a few minutes behind the very latest lap on a live
    race, since indexing runs on the same 5-minute background tick as event
    phrasing, not synchronously on every request (that would mean an
    embedding-API round-trip on every single chat message)."""
    resolved = _require_session(session_id)
    return analysis.chat_answer(resolved, body.question, max_lap=body.max_lap)
