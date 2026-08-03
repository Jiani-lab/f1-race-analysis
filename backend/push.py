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

VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "")
VAPID_PUBLIC_KEY_B64 = os.environ.get("VAPID_PUBLIC_KEY_B64", "")
# Real bug found via a direct real-data test (not assumed): py_vapid's
# Vapid.from_string() expects the raw base64url-encoded 32-byte private
# scalar, NOT a PEM string -- passing a "-----BEGIN PRIVATE KEY-----" PEM
# blob through it raises "ASN.1 parsing error: invalid length" because it
# tries to base64url-decode the PEM headers as if they were key bytes.
VAPID_PRIVATE_KEY_B64 = os.environ.get("VAPID_PRIVATE_KEY_B64", "")


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
    # Two independently-toggleable notification types (settings page) --
    # both default on so a fresh subscribe reproduces today's behavior
    # exactly, matching the existing single "enable notifications" switch.
    state.setdefault("notify_session_start", True)
    state.setdefault("notify_driver_events", True)
    _save_state(state)


def get_subscription() -> dict | None:
    return _load_state().get("subscription")


def get_preferences() -> dict:
    """Read-side of the settings page. `enabled` reflects whether a real
    subscription is on file, not just whether prefs exist -- browser
    permission can be revoked between visits, so this is the same
    subscription-presence check send_push already relies on."""
    state = _load_state()
    return {
        "enabled": bool(state.get("subscription")),
        "favorite_driver": state.get("favorite_driver"),
        "notify_session_start": state.get("notify_session_start", True),
        "notify_driver_events": state.get("notify_driver_events", True),
    }


def save_preferences(notify_session_start: bool, notify_driver_events: bool, favorite_driver: str | None) -> None:
    state = _load_state()
    state["notify_session_start"] = notify_session_start
    state["notify_driver_events"] = notify_driver_events
    if favorite_driver:
        state["favorite_driver"] = favorite_driver
    _save_state(state)


def clear_subscription() -> None:
    """'Forget this device' -- drops the subscription and both toggles so a
    later re-subscribe starts from the same clean defaults as a first-ever
    signup, rather than resurrecting stale prior choices."""
    state = _load_state()
    state.pop("subscription", None)
    state.pop("favorite_driver", None)
    state.pop("notify_session_start", None)
    state.pop("notify_driver_events", None)
    _save_state(state)


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
            vapid_private_key=VAPID_PRIVATE_KEY_B64,
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
