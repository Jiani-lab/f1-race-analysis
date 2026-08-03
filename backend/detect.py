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

Real gap found from a user report (watched 34 real minutes, zero
notifications): a YouTube upload of the 1995 European GP was on screen for
several of those minutes, real leaderboard overlay and all ("Michael
SCHUMACHER BENETTON RENAULT LAP 9 FASTEST LAP 1:36.521") -- but that
vintage graphic style shows the bare lap count with no "/total" next to it,
which the original pattern required. Widened to make the "/total" part
optional. Note this does NOT fully fix this broadcast style end to end --
retrieval.detect_total_laps still can't determine the race distance without
a "LAP X/Y" reading anywhere in the capture window, so a session detected
from a bare-"LAP N" broadcast will get created (and push its "new session"
notification) but the dashboard's chart/momentum grid will show no data
until/unless a "/total" reading shows up somewhere. Detection and
extraction are two separate gaps; this only closes the first one."""

import re
import time

from mcp_client import call_tool

LAP_PATTERN = re.compile(r"LAP\s*\d+(?:\s*/\s*\d+)?")
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
