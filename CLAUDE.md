# F1 Race Analysis

Live F1 race tracking dashboard. FastAPI backend (`backend/`) + static HTML frontend (`frontend/`).

Repo: https://github.com/Jiani-lab/f1-race-analysis (public)

## Multi-session workflow

This repo is regularly worked on by more than one Claude Code session at once, on the same machine. **Read [`AGENTS.md`](AGENTS.md) before starting any task** — it's the coordination protocol (pull → read status files → work → write status files → commit/push) and the real problems it exists to prevent. `CURRENT-STATUS.md`, `PROGRESS.md`, and `TODO.md` are the status files it points to.

## Git workflow

This project is tracked on GitHub so changes are recorded and can be rolled back, and so others can see progress.

- After making a meaningful set of changes, commit them with a clear message.
- Push to `origin main` after committing, unless the user says otherwise.
- Never commit `.env` or files under `backend/sessions/` (already covered by `.gitignore`) — double-check `git status` before staging if anything looks new there.
- Stage only what you actually authored — see AGENTS.md's note on not bundling another session's in-progress, unrelated changes into your own commit.
