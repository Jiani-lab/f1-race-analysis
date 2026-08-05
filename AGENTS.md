# Working on this repo (for any Claude Code session, including you)

This repo regularly has more than one Claude Code session working on it at
the same time, on the same machine, in the same working directory — not a
hypothetical, it's happened repeatedly already (dev server port fights,
one session's uncommitted work getting mistaken for another's, real
duplicated effort). There's no locking mechanism and no orchestrator
between sessions; this file plus three small status files are the entire
coordination mechanism. It only works if every session actually follows
it, including you, right now, on whatever task you were just given.

## The loop

**① Pull first.** `git pull --rebase` before touching anything. If it
fails because you already have unstaged changes from earlier in this same
task, that's fine — just don't skip checking whether origin moved.

**② Read before you write.** Before doing any work, read (in this order):
this file, then [`CURRENT-STATUS.md`](CURRENT-STATUS.md),
[`PROGRESS.md`](PROGRESS.md), [`TODO.md`](TODO.md). CURRENT-STATUS tells
you what's actually live and how the pieces fit together; PROGRESS tells
you what just happened (so you don't redo it or contradict a decision made
an hour ago by a session you never talked to); TODO tells you what's
genuinely still open versus already decided.

**③ Do the work.**

**④ Write it down before you're done.** Append an entry to `PROGRESS.md`
(new entries go at the top, see that file's own header for the format) and
update `TODO.md` — check off what you finished, add anything new you
surfaced. If what you built changes the architecture picture (new service,
new external dependency, a constraint that no longer holds), update
`CURRENT-STATUS.md` too — that one's a snapshot, not a log, so edit it in
place rather than appending.

**⑤ Commit and push back.** Stage and commit **only what you actually
authored** — run `git status`/`git diff --stat` first, and if something
unrelated shows up modified (another session's in-progress work), leave it
unstaged for that session to commit on its own terms. Write a real commit
message (see CLAUDE.md's existing git-workflow notes). Push to `origin
main` when done, per CLAUDE.md, unless the user said otherwise for this
task.

## A few things that have actually gone wrong before, so they're spelled out here

- **Don't fight over the dev server.** If port 8800 is already taken,
  that's very likely another session's server, not a stale process safe to
  kill. Verify backend logic changes via direct execution
  (`uv run python3 -c "import analysis; ..."`) against real session data
  under `backend/sessions/` instead of restarting a server someone else is
  using.
- **Don't assume a file diff you didn't make is a mistake.** `git status`
  showing a file modified that you never touched almost always means
  another session is mid-task on it, not that something broke. Read the
  diff before reacting to it.
- **worker/ and backend/sync_snapshot.py are a separate, deliberately
  independent sub-project** (the Cloudflare Worker + offline-snapshot
  fallback for f1lightout.com). Per an explicit 2026-08-04 user decision,
  the multi-user portal work (see TODO.md) must not touch these — build
  new portal infra as its own thing even if it ends up sharing the domain.
