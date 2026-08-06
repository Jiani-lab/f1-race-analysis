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
