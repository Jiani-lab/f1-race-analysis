# Current status

A snapshot of what this project actually is and what's actually working,
right now. This is not a changelog (that's [`PROGRESS.md`](PROGRESS.md))
and not a task list (that's [`TODO.md`](TODO.md)) — it's what you'd want
to know before touching the codebase. Edit this file in place as things
change; don't append to it.

## What this is

A live F1 race dashboard, built as a personal test of "screen (Luci OCR) +
audio (Luci ASR) + LLM analysis" as a methodology, that grew into a real
tool: point it at a live broadcast (any platform — B站, YouTube, etc.,
detection isn't platform-locked) and it detects the race, extracts events
and strategy data in real time, answers questions about what happened, and
pushes personalized notifications.

## Architecture, in one picture

```
Luci (local-only, loopback)  →  backend/ (FastAPI, one process per person)  →  frontend/ (static HTML/JS, same-origin)
                                        │
                                        ├─ push.py → browser Web Push (VAPID)
                                        ├─ rag.py → Voyage embeddings + claude -p
                                        └─ watchdog.py → alerts if backend/tunnel/sync die

worker/ (Cloudflare Worker, SEPARATE sub-project)
  → reverse-proxies f1lightout.com to this Mac's tunnel
  → falls back to a read-only KV snapshot (backend/sync_snapshot.py pushes it) if the Mac is offline
  → for an ENDED session, can generate a post-race summary via the Anthropic API directly
    (worker/src/cloud_generate.js + a Worker secret), reading that session's full merged.jsonl
    (also synced by sync_snapshot.py) -- works with the Mac fully off, no `claude -p` involved
```

**Privacy note on the line above, read before extending it further**: raw
commentary text (`merged.jsonl`) leaving this Mac at all is a real
exception, not the default. It is synced ONLY for sessions whose `status`
is `"ended"` (never a live one), and ONLY for cloud_generate.js's own use
(summary generation) -- per an explicit 2026-08-06 user decision that
overrides the *general* "raw commentary stays local" privacy stance for
this one specific, single-user (Jiani-only) use case. This does **not**
carry over to the separate, still-unbuilt Phase 6c multi-user portal
(TODO.md) -- that plan's own exclusion of `merged.jsonl`/`rag_chunks`
stands as previously decided, because a multi-tenant portal (other
people's transcripts, unclear account-isolation boundaries at this point)
is a materially different privacy situation than one person's own
offline-fallback site. Don't treat this decision as blanket permission to
sync more raw data elsewhere without asking again.

**Luci is strictly local-machine-only** (`LUCI_MCP_URL` is always
`127.0.0.1`, no remote mode exists) — this is why "everyone gets their own
live dashboard" means everyone runs their own full local stack
(`./setup.sh`), not one shared server. There is no multi-tenant backend
today, no accounts, no auth, no CORS — `app.py` has exactly one global
`state` (one live race at a time, per process).

## What's actually live and working

- **Detection + capture**: background poll (90s) detects a live F1
  broadcast from on-screen text alone (not platform-restricted since
  Phase 4), pulls Luci vision/audio, merges into per-session JSONL.
- **Auto-generated events**: pit stops, safety cars, lead changes, race
  control notices, team radio — detected deterministically, phrased by
  `claude -p` into headlines/insights, refreshed every 5 min while live.
- **Personalized push notifications**: real Web Push (VAPID), fires with
  zero tabs open once a person has granted permission once. Independent
  toggles for session-start vs. driver-specific events. Per-installation,
  no server-side multi-user state needed (see below).
- **RAG chatbot**: grounded Q&A over a race's own detected events/audio
  (Voyage embeddings + cosine search), falls back to `claude -p` web
  search for general F1 questions or when local coverage is thin. A
  shared project Voyage key ships by default with a per-installation
  token quota; degrades to web-only (no error) once exhausted. Streams
  token-by-token over SSE rather than blocking the request (worst case is
  ~180s: local-grounded attempt + web fallback, each up to 90s) — the
  generation itself runs on a background thread independent of the HTTP
  request, tracked in an in-memory run registry (`analysis._CHAT_RUNS`),
  so a page refresh mid-answer reattaches and replays instead of losing
  the answer. No separate database or persistence: if the backend process
  itself restarts, in-flight runs are gone, same as everything else here.
- **Offline fallback**: `f1lightout.com` stays up (read-only cached
  snapshot) even when this Mac is off, via the separate `worker/` +
  `sync_snapshot.py` sub-project. Ended sessions additionally get a
  cloud-generated post-race summary button (Anthropic API called directly
  from the Worker, `thinking: disabled` -- learned the hard way that this
  model's extended thinking otherwise consumes the whole `max_tokens`
  budget on an empty `thinking` block, leaving nothing for the actual
  answer) -- reads that session's full log, synced once per ended session
  and cached forever after (see the privacy note above).
- **Watchdog**: alerts (via push) if the backend, tunnel, or sync loop
  stop responding — added after a real crash-loop went unnoticed.
- **Tests**: `backend/tests/` (pytest, run with `uv run pytest`) covers
  the calendar auto-naming, reconnect dedup, and event-driver-tagging
  logic — the three pure-logic pieces most recently found to have real
  bugs. Not exhaustive (no coverage yet for `push.py`, `retrieval.py`'s
  OCR extraction, or `watchdog.py`'s own checks) — add tests alongside
  new pure-logic functions as they're written, same pattern.
- **Onboarding**: `./setup.sh` automates everything scriptable for a
  fresh install (deps, VAPID keygen, .env scaffolding, Luci connectivity
  probe, guided Voyage key setup). See `.env.example` for what's left
  manual and why.

## What's designed but not built

- **Multi-user portal** (so a friend can log into a website and see their
  own races without you doing anything): planned as fully independent new
  infrastructure, not touching `worker/`. See `TODO.md` — blocked on an
  account-mechanism decision.

## Known constraints worth knowing before you change something

- One `state` object per backend process — no concept of multiple
  concurrent races or multiple users in one running server.
- No auth anywhere in `backend/`. Every endpoint is trusted-local-only.
- Luci's `app` field is unreliable (often null) — detection and event
  logic depend on on-screen OCR text, not app identity.
- `frontend/module-*.html` are design exploration/preview files, not part
  of the live site — don't treat their design choices (or design-hook
  findings on them) as bugs in the real UI (`home.html`, `index.html`,
  `chat.html`, `settings.html`). (The sibling `style-0N-*.html` mockups
  from 2026-07-31 were removed 2026-08-06 — confirmed superseded by the
  Saira Condensed restyle already applied to the real site.)
