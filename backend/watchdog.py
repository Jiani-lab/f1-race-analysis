"""Watches the three locally-run F1 dashboard services (backend, tunnel,
sync) and pushes a real notification if any of them stop working -- this
exists because right now the only way anyone finds out something broke is
noticing the site is down (2026-08-05: the backend LaunchAgent crash-looped
on a port conflict for a while before anyone noticed, and separately, the
PATH bug that silently broke every `claude -p` call went unnoticed until a
manual check).

Deliberately calls push.send_push() directly instead of going through the
backend's own HTTP API -- the whole point is to still be able to alert when
the backend itself is the thing that's down, so routing through it would
defeat the purpose. Placed in backend/ (not imported by app.py, run as its
own standalone process) so `import push` resolves without needing a
sys.path hack: Python auto-adds a directly-run script's own directory to
sys.path, same reason sync_snapshot.py can `import` nothing from backend/
at all and stays fully decoupled -- this one takes the opposite tradeoff on
purpose, since re-implementing push.send_push's VAPID/pywebpush logic
standalone would be real duplication for zero benefit.
"""

import subprocess
import time
import urllib.request

import push

CHECK_INTERVAL_SEC = 120
# Re-alerting every 2 minutes for an issue that's still ongoing would be
# noise, not signal -- once notified, wait this long before repeating the
# same alert (a genuine recovery still fires immediately, no cooldown).
ALERT_COOLDOWN_SEC = 30 * 60

SERVICES = {
    "com.f1dashboard.backend": "F1 backend (uvicorn)",
    "com.cloudflare.f1dashboard": "Cloudflare tunnel",
    "com.f1dashboard.sync": "KV snapshot sync",
}

_last_alert_at: dict[str, float] = {}
_was_down: dict[str, bool] = {}


def _launchctl_running(label: str) -> bool:
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            parts = line.split()
            # launchctl list columns: PID, last-exit-status, label -- PID is
            # "-" when the job isn't currently running (see the real crash-
            # loop case this was built from: PID showed "-" with a nonzero
            # exit status once launchd gave up retrying).
            if len(parts) >= 3 and parts[-1] == label:
                return parts[0] != "-"
        return False  # not in the list at all -- never loaded, or label typo
    except Exception:
        return False


def _backend_responding() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8800/", timeout=8) as r:
            return r.status == 200
    except Exception:
        return False


def _alert_once(key: str, title: str, body: str) -> None:
    now = time.time()
    if now - _last_alert_at.get(key, 0) < ALERT_COOLDOWN_SEC:
        return
    push.send_push(title, body, "/")
    _last_alert_at[key] = now
    print(f"[watchdog] ALERT sent: {title} -- {body}")


def _track(key: str, healthy: bool, down_title: str, down_body: str, up_title: str, up_body: str) -> None:
    if not healthy:
        _alert_once(key, down_title, down_body)
    elif _was_down.get(key):
        push.send_push(up_title, up_body, "/")
        print(f"[watchdog] recovery: {key}")
    _was_down[key] = not healthy


def check_once() -> None:
    for label, human_name in SERVICES.items():
        running = _launchctl_running(label)
        _track(
            f"svc:{label}", running,
            down_title=f"{human_name} is down",
            down_body=f"launchctl shows {label} not running -- check the Mac.",
            up_title=f"{human_name} recovered",
            up_body=f"{label} is running again.",
        )

    responding = _backend_responding()
    _track(
        "backend:http", responding,
        down_title="F1 dashboard not responding",
        down_body="Backend process may be up but isn't answering HTTP requests on :8800.",
        up_title="F1 dashboard responding again",
        up_body="Backend is answering HTTP requests normally.",
    )

    if all(not v for v in _was_down.values()):
        print(f"[watchdog] all clear ({time.strftime('%H:%M:%S')})")


def main() -> None:
    print("[watchdog] health monitor starting")
    while True:
        try:
            check_once()
        except Exception as e:  # noqa: BLE001 -- keep the loop alive no matter what
            print(f"[watchdog] check_once errored (will retry): {e}")
        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
