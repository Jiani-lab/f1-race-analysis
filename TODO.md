# TODO

Genuinely open work, grouped by area. Check items off in place; add new
ones under the right section (or a new one) as they surface. If something
here turns out to already be done, delete it rather than leaving it
checked — a done item isn't a todo.

## README / GitHub discoverability (2026-08-11)

- [ ] Record a real demo GIF/short video (event timeline populating + an
  LLM commentary line landing) and drop it into the README hero section —
  this is the single biggest missing piece; a placeholder comment marks
  the spot in `README.md`.
- [x] ~~Once `frontend/*.html`'s in-flight rename/restyle settles, do a
  final pass for any stray Chinese UI strings~~ — checked post-rename
  (2026-08-11): `home.html`'s "B站" swapped for "Bilibili" to match the
  spelled-out convention README/CURRENT-STATUS.md already settled on;
  the one remaining fragment, `index.html`'s direction comment quoting
  real captured commentary audio as evidence for its data claims, is not
  UI copy and stays as-is.
- [ ] Confirm MIT is actually the intended license (added 2026-08-11 as
  the trending-repo default) — swap `LICENSE` if not.

## Home page + site nav (2026-08-11)

`/` is now a real landing page (`home.html`); the old race list moved to
`/races` (`races.html`). All 5 real pages share one top nav. Full picture
in `CURRENT-STATUS.md`'s "Site navigation" bullet.

- [ ] **Produce the actual demo video** — plan finalized and mostly
  captured, see `frontend/demo-video-storyboard.md`'s "Capture status".
  Shots 2/3/5/6 (real UI: survey, event feed, question, streamed answer)
  are captured for real via Playwright, raw clips at
  `frontend/video/_raw/` (gitignored). Still needed: shot 4 (the desktop
  notification banner — has to be real screen recording on the user's own
  browser, OS-level UI can't be captured by an isolated automation
  instance), the two Pexels stock clips for shots 1/1b (links in the
  storyboard, needs a real browser click to download), the BGM bed, and
  the final cut/composite. Drop the finished file at
  `frontend/video/demo-walkthrough.mp4` (gitignored) — `home.html`'s
  placeholder swaps out on its own, no code change needed.
- [ ] **Status-note text shows the wrong session's ID on `/race`** — found
  while capturing the demo video (2026-08-12): `index.html`'s status-note
  (the small grey "session race-xxxxx" text) renders `s.session_id` from
  `/session/status`, which reflects the *backend's global live-tracking
  state* (whichever session it last auto-resumed on startup), not the
  page's own `SESSION_ID` from the URL. Cosmetic today (everything else on
  the page — title, events, battles — correctly follows the URL's
  session), but worth fixing so the note never shows an unrelated
  session's ID; either scope that fetch to `SESSION_ID` or suppress the
  note when they don't match instead of silently showing the mismatched
  one.
- [ ] The cross-page CSS token consolidation already tracked below (design
  critique follow-ups) should fold the new `.site-nav` component in too —
  it's currently duplicated verbatim across all 5 files' own `<style>`
  blocks, same drift risk as everything else in that TODO.

## Phase 6c — multi-user portal (f1lightout.com login, see CURRENT-STATUS.md)

- [ ] **Blocked on a decision, not on effort**: account mechanism —
  GitHub OAuth (no email infra needed, but excludes non-GitHub friends) vs
  magic-link email vs something else. Needs the user's call.
- [ ] Sync protocol: `backend/sync_client.py` (new), pushes
  `strategy_trend.json`/`events.json`/`race_meta.json`/`retirements.json`
  + `replay_cutoffs` (needs to start being persisted, currently
  computed-on-demand) to a new portal endpoint. Deliberately excludes
  `merged.jsonl` and `rag_chunks`/`rag_embeddings` (privacy — raw
  commentary text stays local).
- [ ] New independent Cloudflare Worker project (e.g. `portal/`), own
  KV/D1, own path (`f1lightout.com/app/*` or a subdomain) — must not
  touch `worker/` or `sync_snapshot.py`.
- [ ] `frontend/index.html`'s `api()` helper needs an overridable
  `API_BASE` so the same HTML/JS can be served by the portal.
- [ ] No changes needed to `push.py` — notifications stay fully local-per-
  person, the portal is view-only. (Noted here so nobody "fixes" this by
  accident.)

## Offline cloud-side generation (worker/, extends the 2026-08-06 work)

- [ ] Only "post-race summary" is built. Catch-up, What-If, and RAG chat
  were the original ask too but deliberately deferred to prove the pattern
  on one feature first — What-If needs multi-turn state (the local version
  uses `claude -p --resume`; the Anthropic API equivalent is just resending
  conversation history, but the Worker needs somewhere to keep the running
  message array per session), and RAG chat additionally needs a second
  external key (Voyage, for the query embedding) before it can retrieve
  anything.
- [ ] `TRUNCATE_CHARS` (700k chars) in `cloud_generate.js` is untested — the
  one real session on record (2238 records) came in under it. A much
  longer session will silently truncate rather than chunk like the local
  `analysis.py` map-reduce pipeline does above `CHUNK_RECORD_THRESHOLD`.

## Design critique follow-ups (2026-08-06, dual-agent critique of home/race/chat/settings, 26/40)

Full report: `.impeccable/critique/2026-08-06T07-07-59Z__frontend-dashboard-home-race-chat-settings.md`.
P0 (status pill color not resetting on backend-failure) and one P2 (What-If
empty-input validation) are already fixed directly. Remaining, in the order
the user chose ("all of it, one at a time"):

- [ ] Accessibility hardening pass (`/impeccable harden`): notification
  badge + account-switcher menu are keyboard-unreachable (`<div onclick>`,
  no tabindex/role); status text and streamed chat answers have zero
  `aria-live` regions; several inputs (`#race-search`, `#whatif-input`,
  chat composers) rely on placeholder-only text with no `<label>`.
- [ ] Page-level hierarchy pass on `index.html` (`/impeccable layout`) —
  the biggest single opportunity from the critique: ~10 co-equal-weight
  sections with no primary focus; make the replay slider the real anchor
  and use the backend's already-computed `notification_worthy` signal to
  visually promote events instead of uniform weight everywhere.
- [ ] `--ink-faint` fails WCAG AA contrast (~3.3:1 on `#050506`) and is
  used for functional metadata, not just decoration (`/impeccable
  colorize`).
- [ ] Consolidate the 4 real pages' independent `<style>` blocks (drifting
  token names/values — `--track`/`--ink-faint`/`.surface` vs `.panel`)
  into one shared stylesheet/token system (`/impeccable extract`).
- [ ] `/impeccable polish` as the final pass once the above land.

## Phase 6d — validate with a real second person

Blocked on 6c. Five things to actually check when it happens (not assume):
- [ ] A real friend can get through `./setup.sh` unassisted, untimed —
  wherever they get stuck is a real gap in the script, not a hypothetical.
- [ ] Their local state (sessions, push subscription) doesn't collide with
  anyone else's.
- [ ] Their notifications reflect their own preferences, not a copy of
  someone else's.
- [ ] **Highest-risk item**: portal sync auth doesn't leak — person A must
  never see person B's race data.
- [ ] The portal view actually stays live during a real race, not just on
  first load.
