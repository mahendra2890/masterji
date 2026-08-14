# Working on this repository

This project is built by several Claude Code sessions running at once — usually
three or four. Nearly every rule here exists because two of them collided.
[WORKFLOW.md](WORKFLOW.md) records the failures they came from.

## Claim the issue before your first edit

Work is dispatched as GitHub issues in `mahendra2890/masterji`. Before you edit
anything, say on the issue that you have it:

```
gh issue comment N --body "Picked this up."
```

Then look once more, immediately before you open the pull request.

**Why.** Nothing in this repository shows which issue a live session has taken.
A worktree stays clean while a session reads, a branch is local until its first
push, and no pull request exists until the work is finished — so four sessions
in flight are indistinguishable from none by any command you can run here. On
14 August 2026 two sessions independently built #152 and #151, the model seam's
token accounting and its circuit breaker. One merged at 23:57. The other opened
its pull request at 00:01, four minutes later, and threw a finished, tested
branch away.

Unlike a duplicated migration number, this leaves no artifact to detect, so a
comment somebody chose to write is the only signal there is. The second check
matters as much as the first: an afternoon here is long enough for someone to
finish the same thing while you are building it.

**Read the issue's comment thread, not only its body.** Decisions are recorded
there, and by convention a wrong issue body is corrected by a comment rather
than an edit — so the body alone can be out of date in a way that looks
authoritative.

## The rules that are not negotiable

Pointed at where they are enforced rather than restated here. A rule
paraphrased in a second place is a rule that will drift, which is a failure this
repository has already had — see *It moved the gate and left three sentences
behind* in [WORKFLOW.md](WORKFLOW.md).

- **One migration leaf per app.** `cd backend && uv run python manage.py
  check_migration_leaf` — before you push, and again before you merge. CI runs
  it on every pull request and on `main`, but see WORKFLOW.md for the case it
  cannot catch.
- **Every builder-visible change ships a changelog entry in the same pull
  request** — one markdown file in
  [backend/coach/changelog/](backend/coach/changelog/README.md), never a data
  migration. That README is the spec.
- **A worktree and a branch per session**, branched from `origin/main`.
- **Open the pull request and stop there.** Merging is not yours to do unless
  you are asked in the session.

## Verify what you build on

Issue bodies cite exact file paths and line numbers, and several pull requests
merge in an afternoon — so a cited line may have moved between the issue being
written and you reading it. Check the specific claim you are about to build on,
and re-measure any number you intend to repeat rather than quoting it from the
issue. That applies to claims you generate yourself: a `grep -c` is not a count
of anything until you look at what it matched.

## Tests

```
cd backend && uv run python manage.py test    # unqualified — accounts/ too
cd backend && uv run ruff check .
npm run test:web
npm run build
```

The suite stubs every model call, and the base case stubs it to raise, so the
default path under test is the deterministic floor rather than the model's
prose.
