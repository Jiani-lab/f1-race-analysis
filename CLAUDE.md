# F1 Race Analysis

Live F1 race tracking dashboard. FastAPI backend (`backend/`) + static HTML frontend (`frontend/`).

Repo: https://github.com/Jiani-lab/f1-race-analysis (public)

## Git workflow

This project is tracked on GitHub so changes are recorded and can be rolled back, and so others can see progress.

- After making a meaningful set of changes, commit them with a clear message.
- Push to `origin main` after committing, unless the user says otherwise.
- Never commit `.env` or files under `backend/sessions/` (already covered by `.gitignore`) — double-check `git status` before staging if anything looks new there.
