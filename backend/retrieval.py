"""Deterministic vision+audio retrieval and merge for one race session.

This is the one part of the pipeline that must be plain code, not
agent judgment -- see the plan doc for why (chunking must be reliable
and repeatable every single time, not re-decided on the fly).

Note on chunking: earlier manual testing hit a "result exceeds maximum
allowed tokens" error -- but that ceiling belongs to the Claude Code
tool-calling harness that was round-tripping results through the chat,
not to Luci's own HTTP API. Calling the HTTP endpoint directly (as this
module does) does not have that limit. We still chunk by time window,
for ordinary reasons: keeping individual HTTP requests fast, bounding
memory, and being able to fetch chunks concurrently.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mcp_client import LuciMCPError, call_tool

VISION_CHUNK_MINUTES = 30
VISION_LIMIT_PER_CHUNK = 500  # Luci's own cap

# audio_transcript_search is keyword-match, not aggregation, and requires
# a non-empty query -- there's no "give me everything" call. Empirically
# (tested against a real 8-min commentary window): a handful of common
# Chinese function words each match dozens of segments and together give
# near-complete coverage of continuous commentary, whereas a narrow list
# of topic words (进站/超车/...) alone caught only ~5 segments out of ~60+
# real ones in the same window. So: sweep with common words for coverage,
# keep the topic words too (harmless, id-deduped) for clarity/robustness
# in case commentary style varies.
AUDIO_SWEEP_WORDS = ["的", "是", "了", "在"]
AUDIO_TOPIC_WORDS = [
    "进站",
    "超车",
    "penalty",
    "调查",
    "safety car",
    "安全车",
    "软胎",
    "中性胎",
    "硬胎",
    "overtake",
    "pit",
]
AUDIO_KEYWORDS = AUDIO_SWEEP_WORDS + AUDIO_TOPIC_WORDS

SESSIONS_DIR = Path(__file__).parent / "sessions"

# ASR occasionally transcribes silence/noise as one character repeated
# hundreds of times -- caught this for real on the first full-race pull: a
# ~1000-char run of "小" that bloated its 15-min chunk's summarization prompt
# past the downstream timeout. Not real commentary, just noise; drop it here
# rather than downstream, since this module is the one place that's supposed
# to own data-quality cleaning (see module docstring).
_REPEAT_CHAR_RE = re.compile(r"(.)\1{19,}")


def _is_degenerate_audio(text: str) -> bool:
    return len(text) >= 40 and bool(_REPEAT_CHAR_RE.search(text))


def _time_chunks(from_ms: int, to_ms: int, chunk_minutes: int) -> list[tuple[int, int]]:
    chunk_ms = chunk_minutes * 60 * 1000
    chunks = []
    start = from_ms
    while start < to_ms:
        end = min(start + chunk_ms, to_ms)
        chunks.append((start, end))
        start = end
    return chunks


def _pull_vision_chunk(from_ms: int, to_ms: int) -> list[dict]:
    entries = []
    offset = 0
    while True:
        result = call_tool(
            "aggregate_range",
            {"from": from_ms, "to": to_ms, "limit": VISION_LIMIT_PER_CHUNK, "offset": offset},
        )
        batch = result.get("entries", [])
        entries.extend(batch)
        if len(batch) < VISION_LIMIT_PER_CHUNK:
            break
        offset += VISION_LIMIT_PER_CHUNK
    return entries


def pull_vision(from_ms: int, to_ms: int) -> list[dict]:
    """Exhaustively pull vision captures for the window, chunked + parallel."""
    chunks = _time_chunks(from_ms, to_ms, VISION_CHUNK_MINUTES)
    all_entries: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(6, len(chunks) or 1)) as pool:
        for batch in pool.map(lambda c: _pull_vision_chunk(*c), chunks):
            all_entries.extend(batch)
    all_entries.sort(key=lambda e: e["timestamp"])
    return all_entries


def pull_audio(from_ms: int, to_ms: int, keywords: list[str] = AUDIO_KEYWORDS) -> list[dict]:
    """Near-complete sweep of commentary (screen) + reactions (mic) audio.

    audio_transcript_search has no "give me everything" mode, so this
    sweeps a fixed list of common words (see AUDIO_SWEEP_WORDS) plus
    topic words, id-deduped -- validated to catch ~all segments in a
    continuous-commentary window, not just topic hits.
    """
    seen_ids = set()
    segments: list[dict] = []
    for source in ("screen", "mic"):
        for kw in keywords:
            result = call_tool(
                "audio_transcript_search",
                {"query": kw, "from": from_ms, "to": to_ms, "source": source, "limit": 500},
            )
            for seg in result.get("segments", []):
                if seg["id"] in seen_ids:
                    continue
                seen_ids.add(seg["id"])
                if _is_degenerate_audio(seg.get("text", "")):
                    continue
                segments.append(seg)
    segments.sort(key=lambda s: s["tStart"])
    return segments


# The "/" between lap and total OCRs as almost anything: a real "/", a
# "|", a stray "1" (visually the closest thing to a thin slash glyph),
# or nothing at all -- "LAP 2/70", "LAP 7170", "LAP 7|70", "LAP 7 1 70"
# all seen on the *same* broadcast, same race. Match non-greedily and
# anchor on the KNOWN total so the engine backtracks to the shortest
# lap-digit read that still lets "...<total>" match at the end, instead of
# accidentally swallowing the total into the lap number (caught exactly
# that bug: "LAP 7170" first extracted as lap 71/21/31, not 7/2/3, before
# anchoring on a trailing total fixed it).
#
# The total itself used to be hardcoded to 70 (this race's distance) --
# that silently breaks on any other race (Monaco is 78 laps, Spa is 44).
# Race distance is constant through a session even though individual reads
# are noisy, so detect it once per session: whichever trailing number shows
# up most often across every "LAP X<sep>Y" candidate IS the total, then
# build the anchored regex from that instead of a hardcoded constant.
_LAP_CANDIDATE_RE = re.compile(r"LAP\s+(\d{1,3})\s*[/|1]?\s*(\d{2,3})\b")
GAP_RE = re.compile(r"([A-Z]{3,})\s*\+?(\d+\.\d+)\s*[Mм]?")

# Some broadcast overlays OCR in column-raster order rather than row order --
# confirmed on a real YouTube-hosted Silverstone broadcast (Phase 4, distinct
# from the bilibili layout GAP_RE targets): all driver names get read as one
# contiguous run, then the literal word "Interval", then all gap values as a
# second contiguous run, e.g. real captured text:
#   "...NORRIS ANTONELLI HADJAR ... PÉREZ - Interval +7.966 +1.300 ... +21.450"
# instead of "NORRIS +0.497 ANTONELLI +1.030 ..." interleaved per row.
# Verified: GAP_RE.findall() on that real text returns [] -- zero matches,
# not wrong ones, because no driver name ever sits directly next to a
# decimal in this layout. This is a second, independent extraction path
# using positional pairing instead of adjacency: names appear in running
# order (1st = leader, who carries no gap value by convention), so
# name[i+1] pairs 1:1 with values[i].
_INTERVAL_BLOCK_RE = re.compile(r"Interval\s+((?:[+-]?\d+\.\d+\s*)+)")
# Unlike KNOWN_DRIVER_CODES (plain-ASCII 3-letter codes only), this layout's
# full surnames can carry accents (PÉREZ, confirmed real) -- a plain [A-Z]
# token pattern truncates at the É and drops that driver's name/value pairing
# by one across the whole frame. Latin-1 accented uppercase range covers it.
_DRIVER_TOKEN_RE = re.compile(r"\b([A-ZÀ-ÖØ-Þ]{3,})\b")
_COLUMNAR_MIN_DRIVERS = 15  # same well-covered-frame bar as WELL_COVERED_MIN_DRIVERS below


def _extract_columnar_gaps(text: str) -> dict[str, float]:
    m = _INTERVAL_BLOCK_RE.search(text)
    if not m:
        return {}
    before = text[: m.start()]
    names_in_order: list[str] = []
    for tok in _DRIVER_TOKEN_RE.findall(before):
        code = _canon_driver(tok)
        if code and (not names_in_order or names_in_order[-1] != code):
            names_in_order.append(code)
    if len(names_in_order) < _COLUMNAR_MIN_DRIVERS:
        return {}  # sparse frame, don't guess
    values = [float(v) for v in m.group(1).split()]
    if len(values) != len(names_in_order) - 1:
        return {}  # count mismatch between names and gaps -- don't guess, skip this frame
    return dict(zip(names_in_order[1:], values))


def detect_total_laps(vision_entries: list[dict]) -> int | None:
    counts: dict[int, int] = {}
    for e in vision_entries:
        for _, total in _LAP_CANDIDATE_RE.findall(e.get("text", "")):
            n = int(total)
            if 30 <= n <= 100:  # plausible F1 race-distance range
                counts[n] = counts.get(n, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _lap_re_for(total_laps: int) -> re.Pattern:
    return re.compile(rf"LAP\s+(\d{{1,2}}?)\s*[/|1]?\s*{total_laps}\b")

# 2026 grid 3-letter codes, as seen on the actual leaderboard overlay.
# Needed because GAP_RE alone also matches sponsor-banner text (e.g.
# "QATAR AIRWAYS", "PIRELLI" fragments) -- caught this as real junk
# ("AIRWAYS", "HOLY", "MOLY", "RELLI" showing up as fake "drivers") on
# the first extraction pass against real Milestone 0 data.
KNOWN_DRIVER_CODES = {
    "PIA", "NOR", "VER", "HAM", "LEC", "ANT", "HAD", "LAW", "LIN", "HUL",
    "GAS", "OCO", "BOR", "COL", "ALO", "BEA", "SAI", "RUS", "ALB", "STR",
    "BOT", "PER",
}
# The "BATTLE FOR Nth" overlay widget (and "IN PIT" driver-status rows)
# spell out full surnames instead of codes for the top few names -- caught
# this because VER/HAM/LEC data was silently thinner than PER/NOR/etc in
# the first real extraction (lap 6-7 used "VERSTAPPEN +0.497 / HAMILTON
# +1.030", which the code-only whitelist dropped entirely). Map every
# full-surname form we've actually observed back to its code; extend as
# new spellings show up. Extended again while building pit-stop detection
# (real "IN PIT" rows spelled out ANTONELLI/LAWSON/NORRIS/RUSSELL/PEREZ/
# ALONSO/HADJAR/PIASTRI/GASLY too, not just the original three).
SURNAME_TO_CODE = {
    "VERSTAPPEN": "VER",
    "HAMILTON": "HAM",
    "LECLERC": "LEC",
    "ANTONELLI": "ANT",
    "LAWSON": "LAW",
    "NORRIS": "NOR",
    "RUSSELL": "RUS",
    "PEREZ": "PER",
    "ALONSO": "ALO",
    "HADJAR": "HAD",
    "PIASTRI": "PIA",
    "GASLY": "GAS",
    # Extended for detect_team_radio() -- the radio-caption overlay spells
    # out full surnames for any driver, not just the handful the
    # BATTLE-FOR/IN-PIT widgets happened to surface first.
    "LINDBLAD": "LIN",
    "HULKENBERG": "HUL",
    "OCON": "OCO",
    "BORTOLETO": "BOR",
    "COLAPINTO": "COL",
    "BEARMAN": "BEA",
    "SAINZ": "SAI",
    "ALBON": "ALB",
    "STROLL": "STR",
    "BOTTAS": "BOT",
    # Confirmed on a real YouTube-hosted Silverstone broadcast (Phase 4) --
    # the accented form is what that overlay actually OCRs, distinct enough
    # from "PEREZ" above that _DRIVER_TOKEN_RE (which allows accented
    # uppercase, unlike KNOWN_DRIVER_CODES's plain-ASCII driver codes) needs
    # its own explicit mapping rather than relying on accent-stripping.
    "PÉREZ": "PER",
}


def _normalize_lap(raw: str) -> int | None:
    """Sanity-guard the lap digits LAP_RE isolated -- reject anything
    outside a plausible F1 lap-count range rather than trust a clearly
    garbled OCR read through."""
    n = int(raw)
    return n if 1 <= n <= 100 else None


def extract_numeric_series(vision_entries: list[dict]) -> tuple[list[dict], int | None]:
    """Best-effort structured extraction: lap number + driver gap deltas per capture.

    This feeds feature E (the trend chart). Validated against real
    Milestone 0 data -- LAP counters and gap deltas OCR cleanly on the
    bilibili broadcast overlay used so far. Silently returns fewer
    points on captures where nothing matches; callers should treat a
    sparse result as a real signal, not a bug.

    Returns (points, total_laps) -- total_laps is None if the race distance
    couldn't be detected at all (e.g. no vision entries yet).
    """
    total_laps = detect_total_laps(vision_entries)
    if total_laps is None:
        return [], None
    lap_re = _lap_re_for(total_laps)
    points = []
    for e in vision_entries:
        text = e.get("text", "")
        lap_match = lap_re.search(text)
        if not lap_match:
            continue
        lap = _normalize_lap(lap_match.group(1))
        if lap is None or lap > total_laps:
            continue
        gaps = {}
        for code, val in GAP_RE.findall(text):
            canonical = SURNAME_TO_CODE.get(code, code)
            if canonical in KNOWN_DRIVER_CODES:
                gaps[canonical] = float(val)
        # Independent second path for column-raster broadcasts (see
        # _extract_columnar_gaps) -- the two are mutually exclusive per
        # capture in practice (a frame is either row-order or column-order,
        # never both), merging is just belt-and-suspenders.
        for code, val in _extract_columnar_gaps(text).items():
            gaps.setdefault(code, val)
        if gaps:
            points.append({"timestamp": e["timestamp"], "lap": lap, "gaps": gaps})
    return points, total_laps


# GAP_RE has no notion of a retired car ("PIA Out" on the leaderboard has no
# trailing number) -- once a driver's row stops carrying a gap, the extractor
# just falls silent for them, which is correct. The bug is what happens
# AFTER: this session's real data confirmed PIA's row shows "Out" from lap 64
# on, but three isolated single-sample "PIA" readings still show up at laps
# 67-69 -- almost certainly GAP_RE matching a fragment of the post-race
# classification screen, not a live gap. First fix hardcoded that one lap
# per session by hand; generalized here into a real detector so the next
# race doesn't need the same manual archaeology -- the broadcast's own "Out"
# marker is machine-readable, no reason to special-case it per session.
OUT_RE = re.compile(r"\b([A-Z]{3,})\s+Out\b")


def detect_retirements(vision_entries: list[dict], total_laps: int | None) -> dict[str, int]:
    """First lap each driver's row is seen marked "Out" on the leaderboard.
    Validated against this session: detects PIA at lap 57 (not the lap 64
    an earlier manual spot-check assumed -- this scans every capture
    instead of a handful of sampled windows, and turned out to coincide
    with a real Virtual Safety Car at the same lap)."""
    if total_laps is None:
        return {}
    lap_re = _lap_re_for(total_laps)
    first_out_lap: dict[str, int] = {}
    for e in vision_entries:
        text = e.get("text", "")
        lap_match = lap_re.search(text)
        if not lap_match:
            continue
        lap = _normalize_lap(lap_match.group(1))
        if lap is None:
            continue
        for code in OUT_RE.findall(text):
            canonical = SURNAME_TO_CODE.get(code, code)
            if canonical not in KNOWN_DRIVER_CODES:
                continue
            if canonical not in first_out_lap or lap < first_out_lap[canonical]:
                first_out_lap[canonical] = lap
    return first_out_lap


def _drop_post_retirement_noise(retirements: dict[str, int], points: list[dict]) -> list[dict]:
    if not retirements:
        return points
    cleaned = []
    for p in points:
        gaps = {
            code: val
            for code, val in p["gaps"].items()
            if code not in retirements or p["lap"] <= retirements[code]
        }
        if gaps:
            cleaned.append({**p, "gaps": gaps})
    return cleaned


def _canon_driver(code: str) -> str | None:
    canonical = SURNAME_TO_CODE.get(code, code)
    return canonical if canonical in KNOWN_DRIVER_CODES else None


# ---------------------------------------------------------------------------
# Structured re-parse fallback for frames flagged as unreliable (see
# .claude/skills/ocr-data-reliability/SKILL.md pattern 1). Real case: LIN and
# LAW's gap values swapped between frames of the same lap because GAP_RE and
# _extract_columnar_gaps both pair a driver-code token with a gap-value token
# by ORDER OF APPEARANCE in Luci's already-flattened OCR text -- that order
# is not stable frame-to-frame. Checked Luci's get_detail tool against real
# data and confirmed every OCR block carries its own screen coordinates
# (focusRect), and a driver's code sits at the same Y as its gap value (e.g.
# real capture 7660: "NOR" at focusRect "460,498,71,25", "+1.7" at
# "569,498,71,25" -- same y=498). Pairing by row instead of by text order is
# a deterministic, no-LLM-call fix for exactly this failure mode -- cheaper
# and more reliable than re-reading the screenshot with a vision model (which
# was the first idea here, but Luci's screenshotPath files turned out to be
# a proprietary format, not real JPEGs -- confirmed by hand, `claude -p`
# can't decode them). Only called for laps that actually show the spread
# signature, not on every capture -- matches the project's existing "no
# per-frame LLM/extra work unless something's actually wrong" principle.
UNRELIABLE_SPREAD_THRESHOLD = 8.0  # seconds; matches frontend's reliableMedian
_GAP_VALUE_RE = re.compile(r"^[+-]?(\d+\.\d+)")


def _parse_focus_rect(rect: str) -> tuple[int, int, int, int] | None:
    try:
        parts = [int(v) for v in rect.split(",")]
        return (parts[0], parts[1], parts[2], parts[3]) if len(parts) == 4 else None
    except (ValueError, AttributeError):
        return None


def _reread_structured_gaps(capture_id: int) -> dict[str, float] | None:
    """Re-derive {driver_code: gap} for one capture from its individually
    positioned OCR blocks, pairing driver and gap tokens by shared row
    (Y-coordinate) instead of by order-of-appearance in flattened text.
    Returns None on any failure -- callers keep the original regex-derived
    reading in that case, never crash the extraction pipeline over this.

    Real bug caught building this against actual data: a first version
    matched blocks to "whichever row was seen first within Y-tolerance",
    which cross-paired an unrelated sponsor-banner fragment ("PER" from a
    Perplexity ad, x=1340) with HUL's real gap value (x=569) on a real
    capture (8568) just because they happened to land within 15px of each
    other vertically -- and silently dropped HUL's own reading in the
    process. The leaderboard's driver/gap columns sit at x < 700 in every
    real capture inspected; sponsor content is always x > 800. Restricting
    to that region, then nearest-Y (not first-found) matching between two
    separate driver/gap lists, fixes it -- verified against 8568 and
    neighboring captures with the real leaderboard's actual columns only."""
    try:
        result = call_tool("get_detail", {"captureId": capture_id})
    except LuciMCPError:
        return None
    blocks = ((result or {}).get("detail") or {}).get("blocks", [])
    if not blocks:
        return None
    ROW_TOLERANCE = 15  # px; real block heights run ~21-30px
    LEADERBOARD_MAX_X = 900  # px; widest real leaderboard row (long surname) reaches ~812, nearest sponsor-text collision risk ("PER" ad fragment) sits at ~1340
    driver_blocks: list[tuple[int, str]] = []
    gap_blocks: list[tuple[int, float]] = []
    for b in blocks:
        rect = _parse_focus_rect(b.get("focusRect", ""))
        if not rect or rect[0] >= LEADERBOARD_MAX_X:
            continue
        y = rect[1]
        text = (b.get("text") or "").strip()
        for tok in _DRIVER_TOKEN_RE.findall(text):
            driver = _canon_driver(tok)
            if driver:
                driver_blocks.append((y, driver))
                break
        gap_match = _GAP_VALUE_RE.match(text)
        if gap_match:
            gap_blocks.append((y, float(gap_match.group(1))))
    paired: dict[str, float] = {}
    used_gap_indices: set[int] = set()
    for y, driver in driver_blocks:
        best_idx, best_dist = None, ROW_TOLERANCE + 1
        for i, (gy, _gap) in enumerate(gap_blocks):
            if i in used_gap_indices:
                continue
            dist = abs(gy - y)
            if dist <= ROW_TOLERANCE and dist < best_dist:
                best_idx, best_dist = i, dist
        if best_idx is not None:
            used_gap_indices.add(best_idx)
            paired[driver] = gap_blocks[best_idx][1]
    return paired or None


def _flag_unreliable_laps(points: list[dict]) -> set[int]:
    """Same spread check as the frontend's reliableMedian (index.html),
    run here so the (more expensive, network-calling) correction below
    only targets laps that actually need it."""
    by_lap_driver: dict[tuple[int, str], list[float]] = {}
    for p in points:
        for code, val in p["gaps"].items():
            by_lap_driver.setdefault((p["lap"], code), []).append(val)
    flagged = set()
    for (lap, _code), vals in by_lap_driver.items():
        if len(vals) >= 2 and max(vals) - min(vals) > UNRELIABLE_SPREAD_THRESHOLD:
            flagged.add(lap)
    return flagged


def correct_unreliable_frames(
    points: list[dict], vision_entries: list[dict], session_dir: Path
) -> list[dict]:
    """For laps whose raw multi-frame readings show the swap-corruption
    spread signature, re-derive each contributing frame's gaps via
    _reread_structured_gaps and replace the regex-derived values wholesale
    for that frame. Cached per capture id to disk (vision_corrections.json)
    so repeated merge_and_write calls during a still-live session don't
    re-hit get_detail for frames already resolved."""
    flagged_laps = _flag_unreliable_laps(points)
    if not flagged_laps:
        return points

    cache_path = session_dir / "vision_corrections.json"
    cache: dict[str, dict | None] = (
        json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    )
    ts_to_capture = {e["timestamp"]: e.get("captureId") for e in vision_entries if e.get("captureId")}

    corrected = []
    cache_dirty = False
    for p in points:
        if p["lap"] not in flagged_laps:
            corrected.append(p)
            continue
        capture_id = ts_to_capture.get(p["timestamp"])
        if capture_id is None:
            corrected.append(p)
            continue
        key = str(capture_id)
        if key not in cache:
            cache[key] = _reread_structured_gaps(capture_id)
            cache_dirty = True
        replacement = cache[key]
        corrected.append({**p, "gaps": replacement} if replacement else p)

    if cache_dirty:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return corrected


# ---------------------------------------------------------------------------
# Structured race-event detection. Each detect_* function is a plain-code
# signal extractor (same "deterministic, not agent judgment" rule as the
# gap/retirement extraction above) -- the LLM only gets involved downstream,
# in analysis.py, to turn these into readable Chinese phrasing. Every regex
# below was checked against this session's real merged.jsonl before being
# written, not guessed.

# Real OCR confirmed: "HAMILTON IN PIT", "VER IN PIT", "BOT IN PIT" etc. --
# same shape as OUT_RE. First pass also matched junk ("YELLOW IN PIT" from
# a race-control banner, OCR-glued garbage like "IAVERSTAPPEN") -- both
# filtered out by _canon_driver's whitelist, same defense as detect_retirements.
PIT_RE = re.compile(r"\b([A-Z]{3,})\s+IN PIT\b")


def detect_pit_stops(vision_entries: list[dict], total_laps: int | None) -> list[dict]:
    """One event per contiguous "IN PIT" run per driver (a car can pit more
    than once in a race -- a VSC-window stop, then a real strategy stop
    later -- so this is NOT just "first lap seen", unlike retirements)."""
    if total_laps is None:
        return []
    lap_re = _lap_re_for(total_laps)
    last_pit_lap: dict[str, int] = {}
    events: list[dict] = []
    for e in vision_entries:
        text = e.get("text", "")
        lap_match = lap_re.search(text)
        if not lap_match:
            continue
        lap = _normalize_lap(lap_match.group(1))
        if lap is None:
            continue
        for raw_code in PIT_RE.findall(text):
            code = _canon_driver(raw_code)
            if code is None:
                continue
            prev = last_pit_lap.get(code)
            if prev is None or lap - prev > 1:
                events.append({
                    "lap": lap, "timestamp": e["timestamp"], "type": "pit_stop",
                    "drivers": [code], "evidence": text[:120],
                })
            last_pit_lap[code] = lap
    return events


# Real OCR confirmed both "SAFETY CAR" and "VIRTUAL SAFETY CAR" (with OCR
# noise like "FiA VIRTUAL ) SAFETY CAR" -- the core phrase still matches).
SAFETY_CAR_RE = re.compile(r"(VIRTUAL\s+)?SAFETY\s+CAR", re.IGNORECASE)


def detect_safety_car_periods(vision_entries: list[dict], total_laps: int | None) -> list[dict]:
    """Dedupe into ranges, not one event per frame -- a real SC/VSC period
    shows up in dozens of consecutive captures of the same lap(s)."""
    if total_laps is None:
        return []
    lap_re = _lap_re_for(total_laps)
    hits: list[tuple[int, int, str]] = []  # (lap, timestamp, type)
    for e in vision_entries:
        text = e.get("text", "")
        m = SAFETY_CAR_RE.search(text)
        if not m:
            continue
        lap_match = lap_re.search(text)
        if not lap_match:
            continue
        lap = _normalize_lap(lap_match.group(1))
        if lap is None:
            continue
        kind = "vsc" if m.group(1) else "safety_car"
        hits.append((lap, e["timestamp"], kind))
    if not hits:
        return []
    hits.sort(key=lambda h: h[0])
    runs: list[list[tuple[int, int, str]]] = [[hits[0]]]
    for hit in hits[1:]:
        if hit[0] - runs[-1][-1][0] > 1:
            runs.append([])
        runs[-1].append(hit)

    events = []
    for run in runs:
        # Majority-vote the kind across the whole run, not just the first
        # hit -- real bug caught here: OCR sometimes drops "VIRTUAL" from a
        # genuine VSC period (stray noise breaking "VIRTUAL ) SAFETY CAR"
        # adjacency), and if that noisy frame happens to be the run's first
        # hit, using it alone mislabels an entire VSC period as a full SC.
        kinds = [k for _, _, k in run]
        kind = max(set(kinds), key=kinds.count)
        lap0, ts0, _ = run[0]
        lap1 = run[-1][0]
        events.append({
            "lap": lap0, "end_lap": lap1, "timestamp": ts0,
            "type": kind, "drivers": [], "evidence": f"{kind} lap {lap0}-{lap1}",
        })
    return events


# Real OCR confirmed: "RACE CONTROL: YELLOW IN PIT LANE" around lap 15-16
# (the BOT-fire moment). OCR concatenates the leaderboard's own digits
# right after the banner text with no real separator, so an unbounded
# character class over-captures lap numbers/gaps into the "banner" --
# capture greedily then truncate at the first digit run in code, not regex.
RACE_CONTROL_RE = re.compile(r"RACE CONTROL:\s*([A-Z][A-Z /]{2,40})")


def detect_race_control_banners(vision_entries: list[dict], total_laps: int | None) -> list[dict]:
    """Raw banner text only -- deliberately NOT sub-classified into
    penalty/investigation/yellow-flag here (that's a judgment call for the
    LLM phrasing step, not a regex's job). Deduped by (lap, banner text)."""
    if total_laps is None:
        return []
    lap_re = _lap_re_for(total_laps)
    seen: set[tuple[int, str]] = set()
    events = []
    for e in vision_entries:
        text = e.get("text", "")
        m = RACE_CONTROL_RE.search(text)
        if not m:
            continue
        lap_match = lap_re.search(text)
        if not lap_match:
            continue
        lap = _normalize_lap(lap_match.group(1))
        if lap is None:
            continue
        banner = re.split(r"\d", m.group(1), maxsplit=1)[0].strip()
        if not banner or (lap, banner) in seen:
            continue
        seen.add((lap, banner))
        events.append({
            "lap": lap, "timestamp": e["timestamp"], "type": "race_control",
            "drivers": [], "evidence": f"RACE CONTROL: {banner}",
        })
    return events


def detect_penalty_mentions(audio_segments: list[dict], vision_entries: list[dict], total_laps: int | None) -> list[dict]:
    """Weaker/noisier signal than race_control banners -- commentary chatter
    mentioning a penalty/investigation, not an official marker. Reuses the
    existing AUDIO_TOPIC_WORDS keywords rather than inventing new ones.
    Approximates a lap number from the nearest vision capture by timestamp
    since audio segments don't carry a lap themselves."""
    if total_laps is None or not vision_entries:
        return []
    keywords = ("penalty", "调查")
    lap_re = _lap_re_for(total_laps)
    lap_by_ts: list[tuple[int, int]] = []
    for e in vision_entries:
        m = lap_re.search(e.get("text", ""))
        if m:
            lap = _normalize_lap(m.group(1))
            if lap is not None:
                lap_by_ts.append((e["timestamp"], lap))
    lap_by_ts.sort()

    def _nearest_lap(ts: int) -> int | None:
        if not lap_by_ts:
            return None
        import bisect
        idx = bisect.bisect_left(lap_by_ts, (ts,))
        idx = min(idx, len(lap_by_ts) - 1)
        return lap_by_ts[idx][1]

    events = []
    for s in audio_segments:
        text = s.get("text", "")
        if not any(kw in text for kw in keywords):
            continue
        lap = _nearest_lap(s["tStart"])
        if lap is None:
            continue
        events.append({
            "lap": lap, "timestamp": s["tStart"], "type": "penalty_mention",
            "drivers": [], "evidence": text[:120],
        })
    return events


# Well-covered-lap threshold for lead-change detection, see note in
# detect_lead_changes: over half this session's laps (32/61) have fewer
# than 10 of 22 known drivers with any gap reading at all -- almost
# certainly frames where the broadcast showed a narrower widget (replay,
# in-car cam, "BATTLE FOR Nth" close-up) instead of the full grid, not
# laps where most of the field vanished. Validated by hand against this
# session: coverage counts cluster into two groups (mostly under 12, or
# 15+), so 15 is a real gap in the data, not an arbitrary round number.
WELL_COVERED_MIN_DRIVERS = 15

# Even on a well-covered lap, a SINGLE driver's row can still be the one OCR
# misses that specific frame (blur, overlap, whatever) while everyone else
# reads fine -- caught this for real: lap 33 flagged ANT as the sole missing
# driver (looked exactly like a lead change), but the real OCR header text
# for that lap plainly shows PIA still marked "Leader"/"Interval", and NOR
# only takes over at lap 34. A one-off row miss on ANT, not a real
# leadership change. Requiring the same candidate to repeat across several
# consecutive well-covered laps (not necessarily consecutive calendar laps,
# since sparse laps are skipped) filters this out -- a real change persists,
# a stray miss doesn't.
LEAD_CHANGE_MIN_CONSECUTIVE = 2


def detect_lead_changes(points: list[dict], total_laps: int | None, retirements: dict[str, int]) -> list[dict]:
    """Implicit-leader inference: on a well-covered lap, whichever known
    driver has NO gap reading (excluding already-retired drivers) is the
    one everyone else's gap is measured against -- the leader. Explicitly
    does NOT try this on sparse laps (see WELL_COVERED_MIN_DRIVERS) --
    holds the last confirmed leader forward instead of guessing from a
    frame that's simply missing most of the field, and requires a new
    candidate to repeat (see LEAD_CHANGE_MIN_CONSECUTIVE) before trusting
    it over a single-row OCR miss. Real "<NAME> RACE LEADER" OCR banners
    exist but the driver name isn't reliably adjacent to "RACE LEADER" (the
    team name often sits between them instead) -- deliberately not used as
    the primary signal, only this gap-omission method, which is arithmetic
    over already-validated GAP_RE data."""
    if total_laps is None:
        return []
    by_lap: dict[int, dict[str, float]] = {}
    for p in points:
        by_lap.setdefault(p["lap"], {}).update(p["gaps"])

    candidates: list[tuple[int, str]] = []
    for lap in sorted(by_lap):
        active_codes = {c for c in KNOWN_DRIVER_CODES if retirements.get(c, total_laps + 1) > lap}
        seen = set(by_lap[lap]) & active_codes
        if len(seen) < WELL_COVERED_MIN_DRIVERS:
            continue  # sparse frame, skip rather than guess
        missing = active_codes - seen
        if len(missing) != 1:
            continue  # ambiguous (0 or >1 candidates), skip
        candidates.append((lap, next(iter(missing))))

    events = []
    current_leader = None
    i = 0
    while i < len(candidates):
        lap, cand = candidates[i]
        j = i
        while j < len(candidates) and candidates[j][1] == cand:
            j += 1
        run_length = j - i
        # Seed the very first candidate unconditionally (there's no "previous
        # leader" to falsely announce a change away from -- worst case a
        # noisy seed just means we don't know who led before the data starts,
        # not a fabricated transition). After that, require persistence
        # (LEAD_CHANGE_MIN_CONSECUTIVE) before trusting a NEW candidate over
        # a single-row OCR miss like the ANT case above.
        if current_leader is None or run_length >= LEAD_CHANGE_MIN_CONSECUTIVE:
            if cand != current_leader and current_leader is not None:
                events.append({
                    "lap": lap, "timestamp": None, "type": "lead_change",
                    "drivers": [current_leader, cand],
                    "evidence": f"implicit leader changed from {current_leader} to {cand}, confirmed across {run_length} consecutive well-covered laps starting lap {lap}",
                })
            current_leader = cand
        i = j
    return events


# Real OCR confirmed (backend/sessions/race-1785212472206/merged.jsonl,
# lines 1868/1870): 'HAMILTON RADIO 44 "AND WE GOT 5 SECOND PENALTY FOR
# SPEEDING INTO THE PITLANE"' -- a team-radio caption overlay, distinct from
# both the leaderboard and the RACE CONTROL: banner. Found while building
# personalized notifications: this is the only reliable driver-attributed
# signal for penalty-flavored moments -- the RACE CONTROL: banner for this
# exact same real penalty OCR'd as "HA RACE CONTE IN THE PIT LA AM) NOTED -
# SPEEDING PA nonoonte." (doesn't even match RACE_CONTROL_RE), so trying to
# extract a driver from that banner text is a dead end. Also matches
# non-penalty radio chatter ("WELL, THAT WAS QUITE SPECIAL!") -- phrasing
# (analysis.py) decides what's notification-worthy, this detector just
# surfaces every driver-attributed quote it can find.
TEAM_RADIO_RE = re.compile(r'\b([A-Z]{4,15}) RADIO (\d{1,2})[^"]{0,50}"([^"]{3,160})"')


def detect_team_radio(vision_entries: list[dict], total_laps: int | None) -> list[dict]:
    """One event per distinct radio quote per driver -- the same caption
    stays on screen across several consecutive OCR captures, so dedupe by
    (driver, quote prefix) rather than emitting one event per frame, same
    principle as detect_race_control_banners's (lap, banner-text) dedupe."""
    if total_laps is None:
        return []
    lap_re = _lap_re_for(total_laps)
    seen: set[tuple[str, str]] = set()
    events: list[dict] = []
    for e in vision_entries:
        text = e.get("text", "")
        for raw_code, _num, quote in TEAM_RADIO_RE.findall(text):
            code = _canon_driver(raw_code)
            if code is None:
                continue
            key = (code, quote[:50].strip())
            if key in seen:
                continue
            seen.add(key)
            lap_match = lap_re.search(text)
            lap = _normalize_lap(lap_match.group(1)) if lap_match else None
            if lap is None:
                continue
            events.append({
                "lap": lap, "timestamp": e["timestamp"], "type": "team_radio",
                "drivers": [code], "evidence": f'{code} RADIO: "{quote.strip()}"',
            })
    return events


def _retirement_events(retirements: dict[str, int]) -> list[dict]:
    return [
        {"lap": lap, "timestamp": None, "type": "retirement",
         "drivers": [code], "evidence": f"{code} Out (first seen lap {lap})"}
        for code, lap in retirements.items()
    ]


def detect_events(
    vision_entries: list[dict],
    audio_segments: list[dict],
    points: list[dict],
    total_laps: int | None,
    retirements: dict[str, int],
) -> list[dict]:
    """Single entry point analysis.py's phrasing pass calls -- retrieval.py
    stays the one place new detector types get registered."""
    events = (
        _retirement_events(retirements)
        + detect_pit_stops(vision_entries, total_laps)
        + detect_safety_car_periods(vision_entries, total_laps)
        + detect_race_control_banners(vision_entries, total_laps)
        + detect_penalty_mentions(audio_segments, vision_entries, total_laps)
        + detect_lead_changes(points, total_laps, retirements)
        + detect_team_radio(vision_entries, total_laps)
    )
    events.sort(key=lambda e: e["lap"])
    return events


def merge_and_write(session_id: str, vision_entries: list[dict], audio_segments: list[dict]) -> Path:
    """Normalize both streams into one timestamp-sorted JSONL log."""
    records = []
    for e in vision_entries:
        records.append(
            {
                "timestamp": e["timestamp"],
                "stream": "vision",
                "text": e.get("text", ""),
                "browserUrl": e.get("browserUrl"),
                "screenshotPath": e.get("screenshotPath"),
                "captureId": e.get("captureId"),
            }
        )
    for s in audio_segments:
        records.append(
            {
                "timestamp": s["tStart"],
                "stream": "audio",
                "source": s["source"],
                "text": s["text"],
            }
        )
    records.sort(key=lambda r: r["timestamp"])

    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    log_path = session_dir / "merged.jsonl"
    with log_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    raw_series, total_laps = extract_numeric_series(vision_entries)
    raw_series = correct_unreliable_frames(raw_series, vision_entries, session_dir)
    retirements = detect_retirements(vision_entries, total_laps)
    series = _drop_post_retirement_noise(retirements, raw_series)
    (session_dir / "strategy_trend.json").write_text(
        json.dumps(series, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (session_dir / "retirements.json").write_text(
        json.dumps(retirements, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (session_dir / "race_meta.json").write_text(
        json.dumps({"total_laps": total_laps}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    raw_events = detect_events(vision_entries, audio_segments, series, total_laps, retirements)
    (session_dir / "raw_events.json").write_text(
        json.dumps(raw_events, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return log_path


def refresh_session(session_id: str, from_ms: int, to_ms: int) -> Path:
    """One-shot: pull both streams for a window and (re)write the merged log."""
    vision = pull_vision(from_ms, to_ms)
    audio = pull_audio(from_ms, to_ms)
    return merge_and_write(session_id, vision, audio)
