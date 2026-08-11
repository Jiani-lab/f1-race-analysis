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
- [ ] Once `frontend/*.html`'s in-flight rename/restyle (another session,
  in progress as of this entry) settles, do a final pass for any stray
  Chinese UI strings — at last check only two tiny fragments existed
  (`index.html` line ~4, `home.html` "B站"), low priority.
- [ ] Confirm MIT is actually the intended license (added 2026-08-11 as
  the trending-repo default) — swap `LICENSE` if not.

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
