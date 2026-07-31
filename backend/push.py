"""Real browser push notifications (Service Worker + Push API + VAPID) --
fires even with zero tabs of this site open, as long as the browser was
granted notification permission at least once. Replaces the tab-must-stay-open
polling badge as the primary delivery path (see frontend/index.html's
pollForNotifications, which is kept as a fallback for whenever a tab happens
to be open).

Single-user personal project -- one flat JSON file on disk, same pattern as
analysis.py's _answer_cache_path/_claude_sessions_path, no database. The
subscription lives outside SESSIONS_DIR on purpose: it's a browser/device-level
credential, not tied to any one race.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pywebpush import WebPushException, webpush

load_dotenv()

STATE_PATH = Path(__file__).parent / "push_subscription.json"

VAPID_PRIVATE_KEY_PEM = os.environ.get("VAPID_PRIVATE_KEY_PEM", "").replace("\\n", "\n")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "")
VAPID_PUBLIC_KEY_B64 = os.environ.get("VAPID_PUBLIC_KEY_B64", "")


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def save_subscription(subscription: dict, favorite_driver: str) -> None:
    state = _load_state()
    state["subscription"] = subscription
    state["favorite_driver"] = favorite_driver
    state.setdefault("notif_state", {})
    _save_state(state)


def get_subscription() -> dict | None:
    return _load_state().get("subscription")


def get_favorite_driver() -> str | None:
    return _load_state().get("favorite_driver")


def get_notif_state(session_id: str) -> dict:
    return _load_state().get("notif_state", {}).get(session_id, {"count": 0, "last_fired_ms": 0, "seen_keys": []})


def save_notif_state(session_id: str, notif_state: dict) -> None:
    state = _load_state()
    state.setdefault("notif_state", {})[session_id] = notif_state
    _save_state(state)


def send_push(title: str, body: str, url: str) -> bool:
    """Returns True on a real send, False if there's no subscription to send
    to (not an error -- just means the one-time setup hasn't happened yet).
    A dead/expired subscription (real thing that happens -- browsers can
    invalidate a subscription at any time) clears the stored subscription
    instead of leaving it around to fail silently forever, same
    "degrade honestly, don't crash the caller" principle as the rest of
    this codebase's cache/retry handling."""
    subscription = get_subscription()
    if not subscription:
        return False
    payload = json.dumps({"title": title, "body": body, "url": url})
    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY_PEM,
            vapid_claims={"sub": VAPID_SUBJECT},
        )
        return True
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):  # subscription gone -- browser says so explicitly
            state = _load_state()
            state.pop("subscription", None)
            _save_state(state)
        print(f"[push] send failed (status={status}): {e}")
        return False
