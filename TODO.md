# TODO

Genuinely open work, grouped by area. Check items off in place; add new
ones under the right section (or a new one) as they surface. If something
here turns out to already be done, delete it rather than leaving it
checked — a done item isn't a todo.

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

## Housekeeping

- [ ] `README.md`'s `目录` and `已知限制` sections are still mostly
  Milestone-0-era and don't reflect Phase 2–6 — needs a real rewrite, not
  just the one-line fixes done so far.
- [ ] Unclear whether the 8 `frontend/style-0N-*.html` mockups (2026-07-31)
  are still a live decision to pick from, or superseded by the direct
  Saira Condensed restyle already applied to the real site (2026-08-03) —
  worth confirming with the user; if superseded, consider whether to keep
  them around as reference or remove them.
