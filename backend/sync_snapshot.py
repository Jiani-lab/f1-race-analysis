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
import time
import urllib.request

BACKEND = "http://127.0.0.1:8800"
KV_NAMESPACE_ID = "4327f77bb8f844a3b81ba48b675868bc"
WORKER_DIR = "/Users/waspcn/Projects/f1-race-analysis/worker"
POLL_INTERVAL_SEC = 90
MAX_EVENTS_IN_SNAPSHOT = 10

_last_hash = None


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

    live = next((s for s in sessions if s.get("status") == "active"), None)
    live_session = None
    if live:
        events_resp = _get_json(f"/session/events?session_id={live['session_id']}")
        events = (events_resp or {}).get("events", [])[-MAX_EVENTS_IN_SNAPSHOT:]
        live_session = {
            "session_id": live["session_id"],
            "round": live.get("round"),
            "name": live.get("name"),
            "events": events,
        }

    return {
        "synced_at": int(time.time() * 1000),
        "sessions": sessions,
        "live_session": live_session,
    }


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
    global _last_hash
    print("[sync] snapshot sync loop starting")
    while True:
        snapshot = build_snapshot()
        if snapshot is not None:
            h = content_hash(snapshot)
            if h != _last_hash:
                if push_to_kv(snapshot):
                    _last_hash = h
                    print(f"[sync] pushed new snapshot ({len(snapshot['sessions'])} sessions, "
                          f"live={'yes' if snapshot['live_session'] else 'no'})")
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
