# Progress log

Reverse-chronological. **New entries go at the top of the list below**,
right under this line — don't hunt for "the end" of the file. Keep entries
short (a line or two per meaningful change); the commit itself is the
detailed record, this is just enough for the next session to orient in 30
seconds without reading `git log`. Group same-day work from the same
session under one dated bullet where it makes sense.

---

- **2026-08-05** — Offline fallback page (`worker/`) redesigned for real
  visual parity with the live site (Saira Condensed, checkered-flag mark,
  masthead photo served via a Workers Assets binding so it works
  independent of the origin) plus two real functional gaps fixed: past-
  session cards had no `href` at all (dead clicks), and the KV snapshot
  only ever carried event data for whichever session was live at sync
  time — `sync_snapshot.py` now syncs every session's events, so a fully-
  generated past session actually has content to show once the Mac is
  offline, not just a dead end. Also added a first pytest suite
  (`backend/tests/`, 22 tests) covering the calendar auto-naming,
  reconnect dedup, and event-driver-tagging logic added the day before —
  writing it caught two more real bugs on the spot: a driver-code case-
  normalization bug in `_resolve_event_drivers` (an LLM-returned lowercase
  code would silently fail the exact-match push filter downstream) and an
  incorrect test assumption about calendar slack windows never overlapping
  for closely-spaced races (they can, documented as a known tradeoff
  rather than "fixed" by shrinking slack back to a value that breaks the
  original regression case).
- **2026-08-05** — Added the multi-session coordination protocol itself
  (this file + `AGENTS.md` + `CURRENT-STATUS.md` + `TODO.md`), after
  repeated real friction from concurrent sessions on this repo (port
  fights, misattributed diffs). Also: onboarding automation (`setup.sh`,
  `.env.example`, README rewrite — Phase 6b) and a watchdog that pushes an
  alert if the backend/tunnel/sync loop goes down.
- **2026-08-04** — RAG chatbot web-search fallback for general F1
  questions (Phase 6a) and a per-installation quota for the shared Voyage
  key (Phase 6b's key decision). Separately: the offline-fallback
  Cloudflare Worker (`worker/` + `sync_snapshot.py`) shipped, deliberately
  kept as its own independent sub-project. Site-wide restyle to F1's
  bold-italic display typography (Saira Condensed). GP-calendar
  auto-naming for sessions, dedupe for reconnect detections.
- **2026-08-03** — Big day: RAG chatbot (standalone page + race-page
  widget), notification settings page, real photography on the homepage,
  homepage redesign (live race split into its own hero, past sessions
  grouped by year), several real data-integrity bug fixes (OCR gap-reading
  reliability, masthead photo rendering, illustration icons), an
  `ocr-data-reliability` project skill documenting the root causes found
  that day.
- **2026-07-31** — Real browser push notifications (VAPID/Web Push) and 8
  style-direction mockups (`frontend/style-0N-*.html` — previews only,
  never applied to the live site as-is). Added `CLAUDE.md`.
- **2026-07-28** — Initial commit. Milestone 0 validated the core
  methodology (screen OCR + audio ASR + LLM analysis) against a real
  8-minute B站 F1 broadcast recording — see plan doc for the full
  validation writeup.

*(Full phase-by-phase design rationale — what was tried, what was
verified with real data, what's still an open decision — lives in
`.claude/plans/plan-f1-luci-wild-puffin.md`. This log is "what happened,"
that plan doc is "why.")*
