"""Keeps the Cloudflare KV "snapshot" fresh so f1lightout.com has something
real to fall back to when this Mac is off/asleep (see worker/src/worker.js).
Deliberately talks to the local backend over plain HTTP (GET /sessions,
GET /session/events) instead of importing backend internals -- this is a
standalone sync job, not part of the request-serving path, and decoupling
it keeps it simple to run/restart independently.

Incremental by design: only writes to KV when the snapshot content actually
changed (hash comparison), not on every poll tick. Cloudflare's free KV tier
caps writes at 1000/day; a full race generates on the order of a few dozen
real changes, nowhere near that limit -- but polling every tick without the
hash check would burn through it over a long enough session.
"""

import hashlib
import json
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

BACKEND = "http://127.0.0.1:8800"
KV_NAMESPACE_ID = "4327f77bb8f844a3b81ba48b675868bc"
WORKER_DIR = "/Users/waspcn/Projects/f1-race-analysis/worker"
SESSIONS_DIR = Path(__file__).parent / "sessions"
POLL_INTERVAL_SEC = 90
MAX_EVENTS_IN_SNAPSHOT = 10
# Per an explicit 2026-08-04 privacy decision (see TODO.md history), raw
# commentary text (merged.jsonl) and RAG data were deliberately excluded
# from any sync. Superseded 2026-08-05 by an explicit user decision to
# enable cloud-side summary/catchup/whatif/RAG generation for ENDED
# sessions only (never a still-live one) when the Mac is off -- those
# features fundamentally need the raw log, there is no way to build them
# without it. Read directly off disk (not via HTTP) since this runs on the
# same machine as the backend and the data is large/sensitive enough that
# adding a new public HTTP endpoint for it felt like more exposure than
# necessary for a same-machine file read.
SYNCED_LOGS_MARKER = Path(__file__).parent / ".synced_session_logs.json"

_last_hash = None
_synced_logs: set[str] = set()


def _get_json(path: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{BACKEND}{path}", timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001 -- backend may be mid-restart, just skip this tick
        print(f"[sync] fetch {path} failed (will retry next tick): {e}")
        return None


def build_snapshot() -> dict | None:
    sessions_resp = _get_json("/sessions")
    if sessions_resp is None:
        return None
    sessions = sessions_resp.get("sessions", [])

    # Every session's events get synced, not just whichever one is live --
    # a past session's analysis is already fully generated and cached
    # locally (get_phrased_events reads from events.json, no new `claude -p`
    # calls for laps already processed), so this is cheap even though it
    # runs every tick. The whole point of syncing is to make already-done
    # work visible offline, not just today's race -- a snapshot that only
    # ever carried the live session left every past session's own detail
    # page dead once the Mac was off, even though the content already
    # existed on disk.
    for s in sessions:
        events_resp = _get_json(f"/session/events?session_id={s['session_id']}")
        s["events"] = (events_resp or {}).get("events", [])[-MAX_EVENTS_IN_SNAPSHOT:]

    live_session = next((s for s in sessions if s.get("status") == "active"), None)

    return {
        "synced_at": int(time.time() * 1000),
        "sessions": sessions,
        "live_session": live_session,
    }


def _load_synced_logs() -> set[str]:
    if SYNCED_LOGS_MARKER.exists():
        return set(json.loads(SYNCED_LOGS_MARKER.read_text(encoding="utf-8")))
    return set()


def _save_synced_logs(synced: set[str]) -> None:
    SYNCED_LOGS_MARKER.write_text(json.dumps(sorted(synced)), encoding="utf-8")


def push_raw_text_to_kv(key: str, text: str) -> bool:
    """--path=<file> instead of passing text as a CLI argument -- a full
    race's merged.jsonl (~1.1MB for the one real session on record) blows
    past macOS's command-line argument length limit when passed directly
    (confirmed for real: a 95KB session uploaded fine as an arg, the 1.1MB
    one failed with "Argument list too long"). A temp file has no such
    limit."""
    tmp_path = Path(tempfile.gettempdir()) / f"f1sync-{uuid.uuid4().hex}.txt"
    try:
        tmp_path.write_text(text, encoding="utf-8")
        subprocess.run(
            [
                "/opt/homebrew/bin/npx", "wrangler", "kv", "key", "put",
                f"--namespace-id={KV_NAMESPACE_ID}", key, f"--path={tmp_path}", "--remote",
            ],
            cwd=WORKER_DIR, check=True, capture_output=True, timeout=60,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"[sync] wrangler kv put ({key}) failed: {e.stderr.decode(errors='replace')[:300]}")
        return False
    except Exception as e:  # noqa: BLE001 -- keep the loop alive no matter what
        print(f"[sync] wrangler kv put ({key}) failed: {e}")
        return False
    finally:
        tmp_path.unlink(missing_ok=True)


def sync_ended_session_logs(sessions: list[dict]) -> None:
    """Uploads each ENDED session's full merged.jsonl to KV exactly once --
    an ended session's log never changes again (see _records_mtime's own
    reasoning in analysis.py, same fact reused here), so re-uploading it
    every 90s tick forever would be pure waste. A still-active session is
    never touched by this function at all -- cloud-side generation is
    scoped to ended sessions only, on purpose (see the privacy-decision
    note above this module's constants)."""
    global _synced_logs
    for s in sessions:
        sid = s["session_id"]
        if s.get("status") != "ended" or sid in _synced_logs:
            continue
        log_path = SESSIONS_DIR / sid / "merged.jsonl"
        if not log_path.exists():
            continue
        text = log_path.read_text(encoding="utf-8")
        if push_raw_text_to_kv(f"session-log:{sid}", text):
            _synced_logs.add(sid)
            _save_synced_logs(_synced_logs)
            print(f"[sync] uploaded full log for {sid} ({len(text)} bytes) -- one-time, will not repeat")


def content_hash(snapshot: dict) -> str:
    # Exclude synced_at -- it changes every tick regardless of real content.
    stable = {k: v for k, v in snapshot.items() if k != "synced_at"}
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def push_to_kv(snapshot: dict) -> bool:
    payload = json.dumps(snapshot)
    try:
        subprocess.run(
            [
                "/opt/homebrew/bin/npx", "wrangler", "kv", "key", "put",
                f"--namespace-id={KV_NAMESPACE_ID}",
                "snapshot", payload, "--remote",
            ],
            cwd=WORKER_DIR,
            check=True,
            capture_output=True,
            timeout=30,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"[sync] wrangler kv put failed: {e.stderr.decode(errors='replace')[:300]}")
        return False
    except Exception as e:  # noqa: BLE001 -- keep the loop alive no matter what
        print(f"[sync] wrangler kv put failed: {e}")
        return False


def main() -> None:
    global _last_hash, _synced_logs
    _synced_logs = _load_synced_logs()
    print(f"[sync] snapshot sync loop starting ({len(_synced_logs)} session logs already uploaded previously)")
    while True:
        snapshot = build_snapshot()
        if snapshot is not None:
            h = content_hash(snapshot)
            if h != _last_hash:
                if push_to_kv(snapshot):
                    _last_hash = h
                    print(f"[sync] pushed new snapshot ({len(snapshot['sessions'])} sessions, "
                          f"live={'yes' if snapshot['live_session'] else 'no'})")
            sync_ended_session_logs(snapshot["sessions"])
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
