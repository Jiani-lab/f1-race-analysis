"""F1-live-stream detection: is an F1 broadcast currently on screen?

Not app-based (Luci's `app` field is unreliable -- null on every capture
we've seen). Not domain-restricted either anymore -- real data confirmed
`browserUrl` can come back null even on a real capture (not just "wrong",
genuinely absent), and the user explicitly wants any platform that can
stream F1 to work, not just bilibili. Relies on the on-screen text
signature alone: the "LAP X/Y" broadcast-overlay format has now been
confirmed on two real, structurally different broadcasts (a bilibili
Chinese broadcast and a YouTube-hosted official-style Silverstone
broadcast) -- distinctive enough on its own without a domain check.
"""

import re
import time

from mcp_client import call_tool

LAP_PATTERN = re.compile(r"LAP\s*\d+\s*/\s*\d+")
LOOKBACK_MS = 3 * 60 * 1000


def is_f1_live_now() -> bool:
    now_ms = int(time.time() * 1000)
    result = call_tool(
        "filter_by_app_time",
        {"from": now_ms - LOOKBACK_MS, "to": now_ms, "limit": 50},
    )
    for r in result.get("results", []):
        text = r.get("text") or ""
        if LAP_PATTERN.search(text):
            return True
    return False
