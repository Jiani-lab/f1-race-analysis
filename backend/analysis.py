"""The five analysis features (A/B/C/D/E), built on top of the merged log.

A/B/C/D are LLM reasoning over already-retrieved text -> shell out to
`claude -p` (headless mode). No API key needed, reuses your existing
Claude Code auth. E is pure structured data, no LLM involved.
"""

import hashlib
import json
import re
import subprocess
import threading
import uuid
from pathlib import Path

SESSIONS_DIR = Path(__file__).parent / "sessions"

COMMENTATOR_TONE_NOTE = (
    "Writing tone: you're a live TV broadcast commentator, not an analyst writing a quarterly "
    "report. Write in English, conversational, short sentences, with genuine reactions ('what a "
    "move', 'that's costly', 'he's holding on') like you're chatting with a friend watching the "
    "race, not report-speak ('overall, the data shows', 'from a strategic perspective'). But the "
    "content must stay completely faithful to the source records -- the tone can be lively, but "
    "facts can't be invented; say so plainly when you're unsure instead of guessing for effect."
)

ANALYSIS_DEPTH_NOTE = (
    "Important -- don't just restate raw information that's already in the records in different "
    "words, that's something the viewer could already see from watching the broadcast, no added "
    "value. What you should do is analyze and infer:\n"
    "1) Cross-record inference -- e.g. if one frame only clearly shows driver A's lap time/gap, "
    "but nearby frames show other drivers' gaps to the leader, combine them to back out numbers "
    "that were never directly read (driver B's approximate lap pace, position changes). Don't skip "
    "mentioning something just because OCR never captured it directly.\n"
    "2) Compute deltas and trends -- two drivers' gaps to the leader can be subtracted to get the "
    "real gap between the two of them, and whether that gap is growing, shrinking, or oscillating "
    "-- that 'relationship' and 'rate of change' isn't a number that exists directly in the raw data.\n"
    "3) Cross-stream correlation -- vision (on-screen text) and audio (commentary) often each only "
    "carry half the picture; find where they corroborate or explain each other (e.g. a sudden gap "
    "change on screen, and the audio happens to mention a mechanical issue or a pit stop).\n"
    "4) Tire/pit strategy is mandatory, not optional -- soft/hard/medium compound choices, pit lap, "
    "stop duration, whether an undercut/overcut worked, lap-time deltas between compounds -- this "
    "usually only appears in audio, not the on-screen leaderboard, and gets missed easily; whenever "
    "the records mention tires even in passing, combine it with lap-time/gap data to work out the "
    "real impact (e.g. how many seconds per lap a driver gained from a tire advantage, and how many "
    "laps that takes to close a given gap). Don't skip it just because the source mentions are scattered.\n"
    "Only conclusions that required this kind of inference are worth writing; don't just restate "
    "what one record said."
)

RULE_LOOKUP_SYSTEM_NOTE = (
    "You are summarizing what race commentary literally said near a moment in an F1 broadcast. "
    "Only report what the transcript actually says. Do not independently adjudicate FIA rules or "
    "state a rules verdict as fact -- you have no authoritative rulebook here, only commentary text. "
    "If the transcript doesn't mention a rule, say so plainly instead of guessing."
)

WHATIF_SYSTEM_NOTE = (
    "You are constructing a counterfactual ('what if') race strategy scenario, grounded in the real "
    "race data provided plus general F1 strategy knowledge (tire degradation, pit-stop time loss, etc). "
    "This is speculative reasoning, not a verified outcome. Your answer MUST be explicitly framed as a "
    "reasoned hypothesis (state your assumptions), never as a confident, certain conclusion."
)


# This project's own earlier measurement: concurrent `claude -p` calls
# measurably slow each other down rather than running in parallel (chunks
# that ran fine solo blew past their timeout when 2-3 ran at once). Once the
# background event-refresh loop (app.py) exists alongside user-triggered
# catchup/summary/whatif/events, both would shell out to `claude -p`
# independently with no coordination. A single lock around every call
# funnels all of them (existing endpoints included, no call site changes
# needed) through one at a time -- a user request may wait behind a
# background refresh tick, but neither ever silently slows the other down.
_CLAUDE_LOCK = threading.Lock()


def _run_claude(
    prompt: str, timeout: float = 240.0, cli_session_id: str | None = None, resume: bool = False
) -> str:
    """cli_session_id + resume=True reuses an existing `claude -p` session
    (via --resume) instead of starting a fresh one -- the race context sent
    on the first call stays in that session's own history, so a follow-up
    call only needs to send the new question, not the whole body again.
    cli_session_id + resume=False pins a *new* session to that id (via
    --session-id) so it can be resumed later. Verified for real: a second
    `claude -p --resume <id> "..."` call correctly recalled content only
    given in the first call, without it being resent."""
    cmd = ["claude", "-p"]
    if cli_session_id:
        cmd += ["--resume", cli_session_id] if resume else ["--session-id", cli_session_id]
    cmd.append(prompt)
    with _CLAUDE_LOCK:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed: {result.stderr}")
    return result.stdout.strip()


def _load_log(session_id: str) -> list[dict]:
    log_path = SESSIONS_DIR / session_id / "merged.jsonl"
    if not log_path.exists():
        return []
    with log_path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _records_mtime(session_id: str) -> float:
    """Freshness key for the caching/session-reuse below: an ended race's
    merged.jsonl never changes again, so anything keyed on this mtime stays
    valid forever; a still-live race's file gets rewritten as new laps come
    in, which naturally invalidates stale cache entries/CLI sessions instead
    of needing a separate live/ended flag threaded through every call."""
    path = SESSIONS_DIR / session_id / "merged.jsonl"
    return path.stat().st_mtime if path.exists() else 0.0


def _claude_sessions_path(session_id: str) -> Path:
    return SESSIONS_DIR / session_id / "claude_sessions.json"


def _get_claude_session(session_id: str, feature: str, mtime: float) -> str | None:
    path = _claude_sessions_path(session_id)
    if not path.exists():
        return None
    entry = json.loads(path.read_text(encoding="utf-8")).get(feature)
    if not entry or entry.get("mtime") != mtime:
        return None
    return entry.get("cli_session_id")


def _save_claude_session(session_id: str, feature: str, cli_session_id: str, mtime: float) -> None:
    path = _claude_sessions_path(session_id)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data[feature] = {"cli_session_id": cli_session_id, "mtime": mtime}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _format_records(records: list[dict]) -> str:
    lines = []
    for r in records:
        if r["stream"] == "vision":
            lines.append(f"[vision {r['timestamp']}] {r['text']}")
        else:
            lines.append(f"[audio/{r['source']} {r['timestamp']}] {r['text']}")
    return "\n".join(lines)


# A full real race session (~100 min, 2000+ records) blows past what one
# claude -p call can chew through -- confirmed by hand: even the milestone-0
# sample (175 records, ~8 min) timed out at 240s on a full-log summary. Above
# this many records, map-reduce instead of dumping the raw log into one
# prompt: cheap, strictly-factual per-chunk extraction (map, cached to disk
# so repeat calls don't redo it), then the tone/analysis prompt runs on the
# much smaller combined notes (reduce) instead of the raw log.
CHUNK_RECORD_THRESHOLD = 400
CHUNK_WINDOW_MS = 8 * 60 * 1000  # measured: a 15-min/~340-record chunk took 108s
# solo and still timed out under real conditions -- halving the window keeps
# each individual claude -p call comfortably inside the timeout.


def _chunk_records(records: list[dict], window_ms: int = CHUNK_WINDOW_MS) -> list[list[dict]]:
    if not records:
        return []
    chunks: list[list[dict]] = []
    current: list[dict] = []
    window_start = records[0]["timestamp"]
    for r in records:
        if current and r["timestamp"] - window_start >= window_ms:
            chunks.append(current)
            current = []
            window_start = r["timestamp"]
        current.append(r)
    if current:
        chunks.append(current)
    return chunks


def _extract_chunk_notes(records: list[dict]) -> str:
    """Map step: strictly-factual bullet extraction over one ~15-min window.
    No commentator tone here on purpose -- this output gets fed back into the
    reduce-step prompt, so it needs to be small and trustworthy, not stylish."""
    prompt = (
        "Below is a mixed vision (on-screen text) + audio (commentary) record of one ~15-minute "
        "window of an F1 broadcast, sorted by time. Extract the key facts from this window as "
        "short bullet points: lap range, position changes, pit stops, overtakes, incidents/"
        "penalties, team strategy mentions, driver status anomalies. Only write information that "
        "clearly appears in the records -- don't speculate or add anything, full sentences not "
        "required.\n\n" + _format_records(records)
    )
    return _run_claude(prompt, timeout=200.0)


def _get_chunk_notes(session_id: str, records: list[dict]) -> str:
    path = SESSIONS_DIR / session_id / "chunk_notes.json"
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    chunks = _chunk_records(records)
    missing = [c for c in chunks if str(c[0]["timestamp"]) not in cache]
    # Serial, not pooled, and written to disk after EVERY chunk -- not just
    # at the end. Found the hard way: the old batched-pool version only
    # wrote the cache once ALL chunks succeeded, so a single slow/timed-out
    # chunk threw away every other chunk's already-completed work, and each
    # retry started from zero. Concurrency was also making individual
    # `claude -p` calls slower, not faster (measured: solo chunks that ran
    # fine under load elsewhere still blew past 150s/200s timeouts when run
    # 2-3 at once) -- serial is both more reliable and, empirically, faster
    # per call here. A genuinely timed-out chunk degrades to a placeholder
    # instead of failing the whole summary -- honest about the gap rather
    # than silently dropping that window's events.
    for chunk in missing:
        key = str(chunk[0]["timestamp"])
        try:
            cache[key] = _extract_chunk_notes(chunk)
        except subprocess.TimeoutExpired:
            cache[key] = "(This window timed out during processing -- no summary generated. The raw records are still fully preserved in merged.jsonl.)"
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return "\n\n".join(
        f"[{c[0]['timestamp']}–{c[-1]['timestamp']}]\n{cache[str(c[0]['timestamp'])]}" for c in chunks
    )


def _body_for(session_id: str, records: list[dict]) -> tuple[str, str]:
    """Returns (body_text, source_note) -- chunked notes + a note saying so
    above the threshold, raw formatted records + a plain note below it."""
    if len(records) > CHUNK_RECORD_THRESHOLD:
        return _get_chunk_notes(session_id, records), "(large volume, pre-extracted into 15-minute-window notes, still fully covering the whole race)"
    return _format_records(records), "(mixed vision + audio records, sorted by time)"


def _answer_cache_path(session_id: str) -> Path:
    return SESSIONS_DIR / session_id / "answer_cache.json"


def _cached_answer(session_id: str, feature: str, cache_key: str, mtime: float) -> str | None:
    """Real complaint this fixes: clicking "Generate race summary" (or the
    same catchup window) twice re-ran a full `claude -p` call -- and
    resent the whole race body -- for a question that was already answered
    with an identical input. Keyed on _records_mtime so an ended race's
    answer is cached forever and a live race's cache auto-invalidates the
    moment new data actually arrives, no separate live/ended flag needed."""
    path = _answer_cache_path(session_id)
    if not path.exists():
        return None
    entry = json.loads(path.read_text(encoding="utf-8")).get(feature, {}).get(cache_key)
    if not entry or entry.get("mtime") != mtime:
        return None
    return entry.get("text")


def _save_answer(session_id: str, feature: str, cache_key: str, mtime: float, text: str) -> None:
    path = _answer_cache_path(session_id)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.setdefault(feature, {})[cache_key] = {"mtime": mtime, "text": text}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def catchup(session_id: str, since_ms: int) -> str:
    records = [r for r in _load_log(session_id) if r["timestamp"] >= since_ms]
    if not records:
        return "Nothing new captured in this window yet (recording may have just started, or nothing changed on screen)."
    mtime = _records_mtime(session_id)
    cached = _cached_answer(session_id, "catchup", str(since_ms), mtime)
    if cached is not None:
        return cached
    body, note = _body_for(session_id, records)
    prompt = (
        f"{COMMENTATOR_TONE_NOTE}\n\n{ANALYSIS_DEPTH_NOTE}\n\n"
        f"Below are the real records from the past stretch of this F1 broadcast {note}. "
        "Tell me what happened in this window, focusing on lap progression, position changes, "
        "pit stops, and overtakes -- don't just restate the raw records one by one.\n\n" + body
    )
    text = _run_claude(prompt)
    _save_answer(session_id, "catchup", str(since_ms), mtime, text)
    return text


def summary(session_id: str) -> str:
    records = _load_log(session_id)
    if not records:
        return "No data was captured."
    mtime = _records_mtime(session_id)
    cached = _cached_answer(session_id, "summary", "full", mtime)
    if cached is not None:
        return cached
    body, note = _body_for(session_id, records)
    prompt = (
        f"{COMMENTATOR_TONE_NOTE}\n\n{ANALYSIS_DEPTH_NOTE}\n\n"
        f"Below are the complete real records from an F1 race {note}. "
        "Write a post-race summary (a few paragraphs at most) covering how the race unfolded, key "
        "events (overtakes/pit stops/safety cars/penalties), and the final position trends.\n\n" + body
    )
    text = _run_claude(prompt)
    _save_answer(session_id, "summary", "full", mtime, text)
    return text


WHATIF_JSON_NOTE = (
    "Output strictly in the following JSON format, no markdown code fences, no text before or after:\n"
    '{"text": "the full reasoning, laid out clearly, can be fairly long", '
    '"verdict": "one-sentence conclusion", '
    '"scenarios": [{"name": "scenario name", "icon": "a single emoji", '
    '"desc": "one short sentence, under 15 words", "probability": integer 0 to 100, '
    '"sentiment": "positive, negative, or neutral (whether this outcome is good, bad, or neutral '
    'for the subject of the hypothesis)"}]}\n'
    "Sort the scenarios array from most to least likely, give 2-4 scenarios, probabilities should "
    "sum to roughly 100."
    "\n\nImportant formatting requirement -- from a real failure case: if the text field quotes real "
    "team radio audio, always wrap it in single quotes ' ', never use a literal double-quote \" "
    "character inside the text field's contents -- that breaks the JSON structure and causes "
    "parsing to fail. Likewise, never nest another complete JSON object inside the text field."
)

_SENTIMENT_COLOR = {"positive": "#17c964", "negative": "#E10600", "neutral": "#f5a623"}


def _coerce_whatif_dict(parsed: dict, fallback_text: str) -> dict:
    scenarios = []
    for s in parsed.get("scenarios", []) or []:
        try:
            scenarios.append({
                "name": s["name"],
                "icon": s.get("icon", "❓"),
                "desc": s.get("desc", ""),
                "probability": max(0, min(100, int(s.get("probability", 0)))),
                "color": _SENTIMENT_COLOR.get(s.get("sentiment"), "#888"),
            })
        except (KeyError, ValueError, TypeError):
            continue
    return {"text": parsed.get("text", fallback_text), "verdict": parsed.get("verdict", ""), "scenarios": scenarios}


def _parse_whatif_json(raw: str) -> dict:
    """Same three-layer parse + graceful degradation as event phrasing
    (_parse_event_json) -- if the model doesn't return clean JSON, fall back
    to the raw text as-is with no scenarios, rather than losing the whole
    answer. The frontend already handles an empty scenarios list.

    Real failure mode caught by hand: on a large/complex prompt the model
    sometimes double-wraps its answer -- returns {"text": "<the entire
    intended JSON object, escaped as a string>"} instead of the flat object
    directly. If the first parse comes back with no scenarios AND its own
    `text` field looks JSON-shaped, try unwrapping one more level rather
    than silently accepting an empty scenario list."""
    for candidate in (raw, *_extract_json_candidates(raw)):
        try:
            parsed = json.loads(candidate)
            result = _coerce_whatif_dict(parsed, raw)
            if not result["scenarios"] and isinstance(parsed.get("text"), str) and parsed["text"].strip().startswith("{"):
                try:
                    inner = json.loads(parsed["text"])
                    inner_result = _coerce_whatif_dict(inner, parsed["text"])
                    if inner_result["scenarios"] or inner_result["verdict"]:
                        return inner_result
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
            return result
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return {"text": raw, "verdict": "", "scenarios": []}


_JSON_FENCE_OBJ_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json_candidates(raw: str) -> list[str]:
    candidates = []
    m = _JSON_FENCE_OBJ_RE.search(raw)
    if m:
        candidates.append(m.group(1))
    m = _BARE_JSON_OBJ_RE.search(raw)
    if m:
        candidates.append(m.group(0))
    return candidates


def _events_digest(session_id: str) -> str:
    """Real bug this fixes: _body_for() on a full race falls back to
    chunk_notes prose, and any chunk that timed out during generation
    degrades to a blank placeholder (see _get_chunk_notes). For this
    session, the one chunk covering the lap 56-57 VSC -- exactly where
    HAM/NOR/LEC pitted and VER/ANT stayed out -- degraded that way, so a
    whatif question about that window had no account of who pitted and
    who didn't. events.json comes from deterministic regex detection, not
    prose summarization, so it can't go blank the same way -- append it
    as a second, always-present fact source instead of relying on the
    chunk prose alone."""
    phrased = events(session_id)
    if not phrased:
        return ""
    lines = []
    for e in phrased:
        lap = f"lap {e['lap']}" + (f"-{e['end_lap']}" if e.get("end_lap") else "")
        drivers = "/".join(e.get("drivers", [])) or "(no specific driver)"
        flag = " (unconfirmed)" if e.get("uncertain") else ""
        lines.append(f"- {lap} [{e['type']}] {drivers}: {e['headline']}{flag}")
    return "\n".join(lines)


def whatif(session_id: str, hypothesis: str) -> dict:
    """Real complaint this fixes: every single What-If question re-sent the
    entire race body (chunk notes + events digest, often thousands of
    tokens) from scratch, even a second unrelated question about the same
    already-loaded race. Session-resume (see _run_claude) means the race
    context only gets paid for once per race -- follow-up questions just
    send the new hypothesis and reuse Claude's own history of the first
    call. Answer-caching (like catchup/summary) doesn't fit here since
    every question is genuinely different content, not a repeat -- session
    continuity is the right mechanism for "same base, new question"."""
    mtime = _records_mtime(session_id)
    existing = _get_claude_session(session_id, "whatif", mtime)
    if existing:
        follow_up_prompt = (
            f"{WHATIF_JSON_NOTE}\n\n"
            f"Another hypothetical question about the same race: {hypothesis}"
        )
        try:
            raw = _run_claude(follow_up_prompt, timeout=400.0, cli_session_id=existing, resume=True)
            return _parse_whatif_json(raw)
        except (RuntimeError, subprocess.TimeoutExpired):
            pass  # session may have expired/been pruned -- fall through to a fresh one

    records = _load_log(session_id)
    body, note = _body_for(session_id, records)
    digest = _events_digest(session_id)
    digest_block = (
        "\n\nBelow is a list of key events detected by deterministic code (pit stops/retirements/"
        "safety cars/lead changes/etc), which does NOT depend on the chunk summaries above that "
        "may be missing due to timeouts and is more reliable -- use this first to confirm specific "
        f"facts like who pitted and who didn't:\n\n{digest}"
        if digest
        else ""
    )
    prompt = (
        f"{WHATIF_SYSTEM_NOTE}\n\n{ANALYSIS_DEPTH_NOTE}\n\n{WHATIF_JSON_NOTE}\n\n"
        f"The user's hypothetical question: {hypothesis}\n\n"
        f"Below are the real records of what actually happened in this race {note}, "
        "as the real data foundation for your simulation:\n\n" + body + digest_block
    )
    # Real measurement: on this session's full ~102-min chunk-notes body
    # (13 windows of real detailed content), a whatif call timed out at the
    # old default 240s -- catchup/summary got re-tuned for full-race scale
    # earlier, whatif never did until this real timeout surfaced it.
    new_id = str(uuid.uuid4())
    raw = _run_claude(prompt, timeout=400.0, cli_session_id=new_id, resume=False)
    _save_claude_session(session_id, "whatif", new_id, mtime)
    return _parse_whatif_json(raw)


def rule_lookup(session_id: str, around_ms: int, window_ms: int = 3 * 60 * 1000) -> str:
    records = [
        r
        for r in _load_log(session_id)
        if r["stream"] == "audio" and abs(r["timestamp"] - around_ms) <= window_ms
    ]
    if not records:
        return "No commentary audio found around this point in time."
    prompt = f"{RULE_LOOKUP_SYSTEM_NOTE}\n\nCommentary records:\n\n" + _format_records(records)
    return _run_claude(prompt)


def strategy_trend(session_id: str) -> list[dict]:
    path = SESSIONS_DIR / session_id / "strategy_trend.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def race_meta(session_id: str) -> dict:
    path = SESSIONS_DIR / session_id / "race_meta.json"
    if not path.exists():
        return {"total_laps": None}
    return json.loads(path.read_text(encoding="utf-8"))


def retirements(session_id: str) -> dict[str, int]:
    path = SESSIONS_DIR / session_id / "retirements.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def replay_cutoffs(session_id: str) -> list[dict]:
    """For each lap 1..TOTAL_LAPS, a real cutoff timestamp + cumulative
    vision/audio record counts up to that lap -- lets the frontend replay
    the race incrementally instead of only ever showing the final state.

    Laps before the first OCR'd "LAP N/70" aren't approximated -- checked
    the raw data directly: this session's very first capture (audio, at
    session start) is only ~660ms before the first vision capture already
    reading "LAP 9/70". That's not an OCR gap during real recording, it's
    that recording itself didn't start until lap 9 was already underway
    (stream detection has a ~90s poll interval). Laps 1-8 genuinely have
    zero captured data for this session, so they're omitted rather than
    interpolated into a fake progression -- the caller should treat the
    first returned lap as where the replay can actually start."""
    records = _load_log(session_id)
    if not records:
        return []
    trend = strategy_trend(session_id)
    lap_first_ts: dict[int, int] = {}
    for p in trend:
        if p["lap"] not in lap_first_ts or p["timestamp"] < lap_first_ts[p["lap"]]:
            lap_first_ts[p["lap"]] = p["timestamp"]
    known_laps = sorted(lap_first_ts)
    if not known_laps:
        return []
    session_end = records[-1]["timestamp"]
    first_known_lap = known_laps[0]
    # Race distance is detected per-session (retrieval.detect_total_laps),
    # not a hardcoded constant -- falls back to the highest lap actually
    # seen if race_meta.json is somehow missing, rather than assuming 70.
    total_laps = race_meta(session_id).get("total_laps") or known_laps[-1]

    vision_ts = sorted(r["timestamp"] for r in records if r["stream"] == "vision")
    audio_ts = sorted(r["timestamp"] for r in records if r["stream"] == "audio")

    def count_upto(sorted_ts: list[int], cutoff: int) -> int:
        import bisect
        return bisect.bisect_right(sorted_ts, cutoff)

    out = []
    for lap in range(first_known_lap, total_laps + 1):
        estimated = False
        if lap in lap_first_ts:
            ts = lap_first_ts[lap]
        else:
            later = next((l for l in known_laps if l > lap), None)
            ts = lap_first_ts[later] if later is not None else session_end
            estimated = True
        out.append(
            {
                "lap": lap,
                "timestamp": ts,
                "vision_count": count_upto(vision_ts, ts),
                "audio_count": count_upto(audio_ts, ts),
                "estimated": estimated,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Pre-race onboarding: "what are you most interested in this race" options.
# Only depends on which race this is (name/round), not on any race data --
# cached once per session_id with no mtime check, unlike the answer cache
# above (that one deliberately invalidates when merged.jsonl changes; this
# one never should, since a race's identity doesn't change mid-broadcast).

INTEREST_OPTIONS_SYSTEM_NOTE = (
    "You're generating a short multiple-choice list for a pre-race onboarding question: "
    "'What are you most interested in watching for in this race?' Use web search to find this "
    "specific race's real current storylines -- championship stakes, a driver's recent form or "
    "incident, a team's strategy gamble, a rookie to watch, a head-to-head rivalry -- and turn "
    "them into 4-6 short, concrete options (under 12 words each) a fan could tap. Prefer options "
    "specific to this exact race weekend over generic ones a fan could pick for any race. If web "
    "search turns up nothing specific and reliable, it's fine to fall back to broader "
    "race-watching angles (the title fight, a specific team's pace, tire strategy) rather than "
    "inventing details you can't verify.\n\n"
    "Output strictly a single JSON object, no text before or after, no markdown code fences, in "
    "this format: "
    '{"options": [{"id": "short-slug", "label": "concrete, race-specific option text"}]}'
)

# Fallback when web search fails/times out or produces nothing usable --
# generic but always valid, so onboarding never blocks on this call.
FALLBACK_INTEREST_OPTIONS = [
    {"id": "championship", "label": "How this affects the championship standings"},
    {"id": "favorite-driver", "label": "How my favorite driver performs"},
    {"id": "strategy", "label": "Tire strategy and pit stop calls"},
    {"id": "battles", "label": "Overtakes and on-track battles"},
]


def _interest_options_path(session_id: str) -> Path:
    return SESSIONS_DIR / session_id / "interest_options.json"


def interest_options(session_id: str, race_name: str) -> list[dict]:
    path = _interest_options_path(session_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["options"]
    prompt = f"{INTEREST_OPTIONS_SYSTEM_NOTE}\n\nThe race: {race_name}"
    try:
        # Shorter timeout than the race-body analysis calls elsewhere in
        # this file -- this only needs a web search + a handful of short
        # strings back, not reasoning over a full race log.
        raw = _run_claude(prompt, timeout=90.0)
        options = None
        for candidate in (raw, *_extract_json_candidates(raw)):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed.get("options"), list) and parsed["options"]:
                    options = [
                        {"id": str(o["id"]), "label": str(o["label"])}
                        for o in parsed["options"]
                        if isinstance(o, dict) and "id" in o and "label" in o
                    ]
                    break
            except (json.JSONDecodeError, ValueError, TypeError, KeyError):
                continue
        if not options:
            options = FALLBACK_INTEREST_OPTIONS
    except (subprocess.TimeoutExpired, RuntimeError):
        options = FALLBACK_INTEREST_OPTIONS
    path.write_text(json.dumps({"options": options}, ensure_ascii=False, indent=2), encoding="utf-8")
    return options


# ---------------------------------------------------------------------------
# Structured event phrasing -- turns retrieval.py's deterministic raw_events
# (lap/type/drivers/evidence, no judgment) into short English broadcast text
# via claude -p. First place in this codebase asking the model for
# parseable JSON rather than prose -- no existing pattern to copy, so the
# parsing has to be defensive (see _parse_event_json).

EVENT_PHRASING_SYSTEM_NOTE = (
    "You're converting a batch of already-confirmed F1 race events into short English broadcast "
    "text, one per event. Each one should only state what that event's evidence text clearly "
    "supports -- don't speculate about information that isn't there, and don't blend in details "
    "from other events. If a given piece of evidence is itself vague or contradictory, mark that "
    "event's uncertain as true and explain why in insight. If an event is genuinely minor and "
    "doesn't meaningfully affect the race narrative (e.g. a routine mid-race pit stop with no "
    "strategic significance), give it a low importance score (0-20) -- don't omit it, still "
    "return it normally.\n\n"
    "Two more fields are for a SEPARATE, much stricter purpose: deciding whether this event is "
    "worth interrupting someone with a push notification while they're watching the race. This "
    "is not the same bar as 'importance' above -- importance is about narrative significance in "
    "general (a routine safety car can be importance 60 for the story of the race but should "
    "never interrupt anyone). notification_worthy must be true for only a small handful of "
    "events in the ENTIRE race -- across a real ~90-minute race with roughly 40-50 total detected "
    "events, expect to mark somewhere around 3-5 as notification_worthy, not more. Only mark it "
    "true for pit-stop-math-changing moments, penalties, retirements of contending drivers, and "
    "points/championship-relevant swings. Routine pit stops, minor gap changes, neutral radio "
    "chatter, and VSC/yellow flags with no lasting consequence are never notification_worthy.\n\n"
    "When notification_worthy is true, notification_hook must contain a short (under 30 words) "
    "forward-looking notification. It must NEVER restate a fact already visible on screen (a "
    "position, a lap number, a gap in seconds, or anything already said in headline) -- that is "
    "explicitly forbidden. Instead it must either (a) project forward using real pit-stop/tire "
    "math (e.g. how many more stops a driver needs at this pace, whether their tires can hold to "
    "the finish), or (b) connect the event to bigger stakes (championship points, season "
    "standings implications). If you can't produce a notification_hook that clears this bar "
    "without just restating the headline, leave notification_worthy false instead.\n\n"
    "suggested_whatif is only for negative events about a specific driver (a penalty, a "
    "retirement, losing the lead or a position) -- a single ready-to-use hypothetical question "
    "(e.g. 'What if Hamilton hadn't pitted when the penalty was issued -- what position would he "
    "be holding now?') that could be fed directly into a what-if simulator. Leave it as an empty "
    "string for anything else, including most notification_worthy events.\n\n"
    "Output strictly a single JSON array, one element per event (same order as the input), no "
    "text before or after, no markdown code fences, each element in this format:\n"
    '{"index": 0, "headline": "one-sentence fact", "insight": "brief inference/significance, '
    'under 25 words", "uncertain": true or false, "importance": integer 0 to 100 (how significant '
    'this event is to the race narrative), "notification_worthy": true or false, '
    '"notification_hook": "", "suggested_whatif": ""}'
)

# Batched, not one claude -p call per event -- measured for real: 5 events
# phrased individually took 88s (~18s/event average), which would put a
# 45-event race (this session) at ~13-15 minutes cold. Batching cut that to
# 325s (~5.4 min) for 44 events across 3 batches -- real improvement, but
# generation time is mostly proportional to total output (44 structured
# JSON entries), not round-trip count, so bigger batches only trim the
# fixed per-call overhead, not the dominant cost. Honest expectation for a
# cold first-load on a real full race: a few minutes, not "1-2 min" --
# correct that assumption in the frontend copy, don't just undersell it.
# Timeout bumped 150s -> 200s (_phrase_event_batch below) after a Phase-5
# smoke test hit the 150s wall on batches as small as 11-20 events, well
# under EVENT_BATCH_SIZE -- likely general system load at the time (the
# server's own background loop was correctly idle, session wasn't "active"),
# not a size-driven problem, but 150s had too little headroom either way.
EVENT_BATCH_SIZE = 25


def _phrase_event_batch(batch: list[dict]) -> list[dict]:
    lines = []
    for i, event in enumerate(batch):
        lap_desc = f"lap {event['lap']}" + (f" to lap {event['end_lap']}" if event.get("end_lap") else "")
        drivers = ", ".join(event.get("drivers", [])) or "(no specific driver)"
        lines.append(
            f"[{i}] type: {event['type']} | {lap_desc} | drivers: {drivers} | evidence: {event['evidence']}"
        )
    # ANALYSIS_DEPTH_NOTE reused verbatim here for its tire/pit-strategy math
    # instructions -- notification_hook's "project forward using real pit-stop
    # math" requirement leans on exactly the same inference muscle already
    # proven out for catchup/summary/whatif, not a separately invented rule.
    prompt = f"{EVENT_PHRASING_SYSTEM_NOTE}\n\n{ANALYSIS_DEPTH_NOTE}\n\n" + "\n".join(lines)
    # Real measurement after switching event phrasing to English: a 5-event
    # batch took 72s (~14.4s/event) -- English write-ups run noticeably more
    # verbose than the old Chinese one-liners did. At EVENT_BATCH_SIZE=25
    # that's ~360s of real generation time, well past the old 200s timeout --
    # both batches of a 44-event regeneration degraded to timeout placeholders
    # because of this, not because anything broke. Bumped with headroom
    # rather than shrinking the batch, same call as the whatif 240s->400s fix.
    raw = _run_claude(prompt, timeout=600.0)
    return _parse_event_batch_json(raw, batch)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)
_BARE_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _extract_json_array_candidates(raw: str) -> list[str]:
    candidates = []
    m = _JSON_FENCE_RE.search(raw)
    if m:
        candidates.append(m.group(1))
    m = _BARE_JSON_ARRAY_RE.search(raw)
    if m:
        candidates.append(m.group(0))
    return candidates


def _degraded_event(event: dict, reason: str) -> dict:
    return {
        "lap": event["lap"],
        "end_lap": event.get("end_lap"),
        "type": event["type"],
        "drivers": event.get("drivers", []),
        "headline": event["evidence"][:60],
        "insight": reason,
        "uncertain": True,
        "importance": 0,
        # A degraded event never clears the (much stricter) notification bar --
        # no write-up means no confident basis for interrupting anyone.
        "notification_worthy": False,
        "notification_hook": "",
        "suggested_whatif": "",
    }


def _parse_event_batch_json(raw: str, batch: list[dict]) -> list[dict]:
    """Three-layer parse (bare array -> fenced -> embedded blob). If the
    whole batch fails to parse, every event in it degrades individually
    (still returns a full-length list, never fewer items than requested) --
    same "honest about the gap, don't crash the caller" principle as
    _get_chunk_notes' TimeoutExpired handling."""
    for candidate in (raw, *_extract_json_array_candidates(raw)):
        try:
            parsed = json.loads(candidate)
            if not isinstance(parsed, list):
                continue
            by_index = {}
            for item in parsed:
                if isinstance(item, dict) and "index" in item:
                    by_index[int(item["index"])] = item
            results = []
            for i, event in enumerate(batch):
                item = by_index.get(i)
                if item is None:
                    results.append(_degraded_event(event, "(missing from the batch result, no write-up generated)"))
                    continue
                try:
                    notification_worthy = bool(item.get("notification_worthy", False))
                    results.append({
                        "lap": event["lap"],
                        "end_lap": event.get("end_lap"),
                        "type": event["type"],
                        "drivers": event.get("drivers", []),
                        "headline": item["headline"],
                        "insight": item.get("insight", ""),
                        "uncertain": bool(item.get("uncertain", False)),
                        "importance": max(0, min(100, int(item.get("importance", 0)))),
                        # Defensive even though the prompt says "only when
                        # notification_worthy" -- never trust the model to
                        # have actually left these blank when it said false.
                        "notification_worthy": notification_worthy,
                        "notification_hook": str(item.get("notification_hook", "")) if notification_worthy else "",
                        "suggested_whatif": str(item.get("suggested_whatif", "")),
                    })
                except (KeyError, ValueError, TypeError):
                    results.append(_degraded_event(event, "(malformed result for this entry, no write-up generated)"))
            return results
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return [_degraded_event(e, "(automatic write-up failed, showing the raw evidence text below)") for e in batch]


def _event_key(event: dict) -> str:
    """Stable hash of (lap, type, drivers) only, not the whole event dict --
    so re-detecting on a slightly wider time window still hits cache for
    events already phrased."""
    raw = json.dumps(
        {"lap": event["lap"], "type": event["type"], "drivers": sorted(event.get("drivers", []))},
        sort_keys=True,
    )
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def get_phrased_events(session_id: str, raw_events: list[dict]) -> list[dict]:
    """Written to disk after EVERY batch -- not just at the end. Same real
    bug already fixed once in _get_chunk_notes: an all-or-nothing write
    means one slow/timed-out batch throws away every other batch's
    already-completed work. A timed-out batch degrades every event in it
    to a placeholder instead of raising, so it never blocks the rest."""
    path = SESSIONS_DIR / session_id / "events.json"
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    missing = [e for e in raw_events if _event_key(e) not in cache]
    for start in range(0, len(missing), EVENT_BATCH_SIZE):
        batch = missing[start : start + EVENT_BATCH_SIZE]
        try:
            phrased = _phrase_event_batch(batch)
        except subprocess.TimeoutExpired:
            phrased = [_degraded_event(e, "(timed out during processing, no write-up generated)") for e in batch]
        for event, result in zip(batch, phrased):
            cache[_event_key(event)] = result
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return sorted(cache.values(), key=lambda e: e["lap"])


def events(session_id: str) -> list[dict]:
    path = SESSIONS_DIR / session_id / "events.json"
    if not path.exists():
        return []
    return sorted(json.loads(path.read_text(encoding="utf-8")).values(), key=lambda e: e["lap"])
