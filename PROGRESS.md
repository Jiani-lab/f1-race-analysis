# Progress log

Reverse-chronological. **New entries go at the top of the list below**,
right under this line — don't hunt for "the end" of the file. Keep entries
short (a line or two per meaningful change); the commit itself is the
detailed record, this is just enough for the next session to orient in 30
seconds without reading `git log`. Group same-day work from the same
session under one dated bullet where it makes sense.

---

- **2026-08-07** — Ran an Impeccable dual-agent design critique across the
  4 real pages (home/race/chat/settings) — 26/40, "Acceptable." Full
  report at `.impeccable/critique/2026-08-06T07-07-59Z__frontend-
  dashboard-home-race-chat-settings.md`. Fixed the two smallest findings
  directly: `index.html`'s status pill kept its old color (often green)
  when a status poll failed instead of reflecting "Backend not
  responding" (new `.status-error` class, reuses the existing `--amber`
  token already used elsewhere for uncertain/caution states); `doWhatIf()`
  had no empty-input guard, unlike the chat composer's own
  `if (!question) return`, so a blank submit could burn a multi-minute
  backend generation for nothing. Remaining findings (a11y hardening,
  `index.html`'s page-level hierarchy, `--ink-faint` contrast, cross-page
  CSS token consolidation) tracked in `TODO.md`, being worked one at a
  time per the user's preference.
- **2026-08-06** — Cloud-side post-race summary generation for ended
  sessions, working with the Mac fully off (`worker/src/cloud_generate.js`,
  calls the Anthropic API directly with a new `ANTHROPIC_API_KEY` Worker
  secret, since Workers cannot shell out to `claude -p`). Required an
  explicit privacy-decision override: `sync_snapshot.py` now uploads each
  ENDED session's full `merged.jsonl` to KV once (never a live session's),
  which the general "raw commentary stays local" stance previously
  excluded -- confirmed with the user this is scoped to this one feature,
  not a blanket policy change (see the privacy note in
  `CURRENT-STATUS.md`, and note the separate Phase 6c portal's own
  exclusion in `TODO.md` is untouched by this). Two real bugs hit and
  fixed getting it working: macOS's command-line argument length limit
  broke the upload for anything over ~1MB (the one real full-race log is
  1.1MB) -- fixed by writing to a temp file and using `wrangler kv key put
  --path=` instead of passing the content as a CLI argument. And the
  model's extended thinking defaulted on and consumed the entire
  `max_tokens` budget on an empty `thinking` block, leaving zero tokens
  for the actual answer (confirmed by dumping the raw API response) --
  fixed with `thinking: { type: "disabled" }`. Verified end-to-end against
  the one real full session on record (2238 records, ~140k prompt tokens):
  a real, well-structured post-race summary generated in ~40s, comparable
  in depth/quality to the local `claude -p` pipeline's own summaries.
- **2026-08-06** — Rewrote README.md's `目录` and `已知限制` sections
  (Housekeeping TODO), which were still Milestone-0-era — `目录` only
  listed the original 5 backend files + `index.html` and never mentioned
  `push.py`/`rag.py`/`watchdog.py`/`sync_snapshot.py`/`worker/`/`tests/`
  that shipped since; `已知限制` still framed the project as "validated on
  an 8-minute test recording, next step is a real race" when it's long
  since been tracking real races for real users. Both now point back to
  `CURRENT-STATUS.md` as the canonical up-to-date source rather than
  duplicating it, to avoid the same rot happening again.
- **2026-08-06** — Removed the 8 `frontend/style-0N-*.html` mockups
  (2026-07-31) after confirming with the user they were superseded, not
  still a live decision — real site (`index.html`) already loads Saira
  Condensed directly via `--sans-display`, while the mockups referenced a
  different, never-updated font variable, confirming the 8-03 restyle had
  already made the choice. Updated the stale cross-reference in
  `CURRENT-STATUS.md`'s "known limitations" section accordingly.
- **2026-08-05** — RAG chatbot rebuilt to stream over SSE with a
  persisted, reconnectable run (`analysis.start_chat_run`/`get_chat_run`,
  `/session/chat/stream/{run_id}`) instead of a single blocking
  request/response — the worst case there (local-grounded attempt + web
  fallback, each up to 90s) meant up to ~180s of zero feedback and the
  answer vanishing outright on a refresh. Modeled on a pattern documented
  in a sibling project's AID_PIM retrospective (streaming + a run that
  survives the browser tab), adapted for `claude -p`'s own
  `--output-format stream-json` and for the fact that our chat needs a
  genuine web-search fallback theirs didn't. Verified end-to-end over real
  HTTP: normal streaming, the NEEDS_WEB_SEARCH→web-fallback handoff (a
  `\x00RESTART\x00` sentinel clears the bubble rather than leaving a
  half-written wrong answer visible), a dropped-and-reconnected SSE
  connection correctly replaying + continuing the same run, and an
  unknown/expired run_id producing a clean error instead of hanging.
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
