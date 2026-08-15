# Backend architecture review — 15 August 2026

A snapshot, not a maintained document. It reviews `main` at `b84c1b0`, and like its
five predecessors it is meant to age. Nothing here is load-bearing for the claims in
[README.md](../../README.md) — if the two ever disagree, the README is the product and
this is an opinion about it.

It follows [13 August (product)](2026-08-13-product-review.md), [14 August (tech and
flow)](2026-08-14-tech-and-flow-review.md), [14 August (UI/UX,
driven)](2026-08-14-ui-ux-drive-review.md), [14 August
(security)](2026-08-14-security-review.md), the [coaching-prose
review](2026-08-14-coach-prose-review.md) and [15 August
(frontend architecture)](2026-08-15-frontend-architecture-review.md).

**None of them read the backend as code to be changed.** The security review read it
for exposure and the tech-and-flow review read the tree at a third this length, two
days and a spend ledger ago. The frontend review made the case for its own existence
by pointing at the file every session collides in; this is the same review pointed at
`backend/coach/views.py`, which is 3,510 lines and where four of the currently open
issues land.

The five proposals live as GitHub issues **#290–#294**.

## How it was produced, and what that is worth

`coach/views.py` read end to end — all 3,510 lines, not sampled — plus `gates.py`,
`bar.py`, `llm.py`, `spend.py`, `guidance.py`, the migration history and the shape of
`tests.py`. Every number below was measured on this tree rather than estimated.

Baseline on this tree: `uv run python manage.py test` is **668 tests, all passing**
(168.7s). `uv run ruff check .` passes. `check_migration_leaf` reports one leaf per app.

Three of the findings below were confirmed by *running* the code rather than by reading
it, with throwaway probes deleted afterwards. That distinction matters here more than it
did in the frontend review: two of the three live in code the suite structurally cannot
reach, so reading was the only thing that could have found them and running was the only
thing that could have confirmed them.

Four limits worth stating:

- **Nothing was driven, and no live model call was made.** Where this review touches
  what a provider actually sends, it says so and says what it could not settle.
- **`prompts.py` (2,490 lines) was read for its seams, not reviewed.** The coaching-prose
  review owns its words; nothing here is a judgement about them. It is plausibly worth
  its own architectural pass and did not get one.
- **`nudges.py`, `weekly.py`, `cohorts.py`, `export.py` and `links.py` were read for
  coupling only.**
- **`accounts/` was left to the security review**, which read it two days ago and whose
  four findings (#252–#255) are still open. Nothing here re-derives them.

## The two findings that lead

### 1. A loop variable in the model seam eats the tool call and the ledger row

`llm.stream_chat` opens its call as `with _attempt(...) as call:`
([`llm.py:275`](../../backend/coach/llm.py#L275)) and then, 24 lines down, iterates the
model's tool-call fragments into a variable of the same name
([`llm.py:299`](../../backend/coach/llm.py#L299)):

```python
with _attempt(settings.LLM_MODEL, stream=True, kind=spend.KIND_CHAT) as call:
    ...
    for chunk in response:
        _note_usage(call, chunk)          # expects the _Call
        ...
        for call in getattr(delta, "tool_calls", None) or []:   # <- rebinds it
```

Python binds a `for` target only when the loop actually iterates, so `call` survives
untouched on a turn with no tool call and is clobbered on every turn with one. From that
point `_note_usage(call, chunk)` is writing the provider's token counts onto a tool-call
fragment instead of onto the object `_attempt` will read.

**Measured**, driving `stream_chat` against a stream shaped the way the seam asks for one
— words, a tool-call fragment, then the usage-only final chunk that
`stream_options={"include_usage": True}` exists to request:

| stream | `spend.record` received | yielded | raised |
| --- | --- | --- | --- |
| no tool call | `{prompt: 1200, completion: 300, total: 1500}` | `delta` | — |
| **with a tool call** | **`{}`** | `delta` only — **no `tool_call`** | `AttributeError` |

Two consequences, and they are not equally certain.

**Certain: the ledger loses the row.** `_Call.usage` never receives the counts, so
`spend.record` is handed `{}` and returns early by its own documented rule — an empty
usage writes nothing. So **every chat turn in which the model calls a tool is missing
from `ModelCall`**, and those are the expensive ones: `suggest_proof` carries a whole
paragraph, and the turns that call tools are the turns doing the product's work. This
holds whatever the provider's objects do, because the counts are written to the wrong
object either way.

That contradicts what the ledger is currently believed to undercount. #261's operator
comment records three limits before anyone quotes a number off `ModelCall`, the first
being that *a call whose provider never reported usage writes no row at all* — described
as deliberate. There is a second cause, it is not deliberate, and it is selective in the
worst way: it drops the costly turns and keeps the cheap ones, so the table does not just
undercount, it skews.

**Not settled here: whether the turn also dies.** With `SimpleNamespace` stand-ins the
`AttributeError` propagates, `ChatView` catches it, and the builder gets `STREAM_BROKE`
with the tool call lost — no drafted proof, no gate check, no close box — while
`_attempt`'s `except` books a failure against the circuit breaker for a provider that
did nothing wrong. Whether litellm's real delta objects raise on `.usage` was not
determined, and there is evidence they may not: **#270 reports a live workshop turn,
driven against `openai/gpt-5.4-mini`, whose `candidates` event arrived** — a tool call
that reached the view. Whoever takes this should settle it with one live call before
assuming either that production is broken or that it is fine.

**Why the suite cannot see it.** Two tests cover the two halves and neither covers the
join:

- `test_the_usage_chunk_does_not_break_the_stream` ([`tests.py:313`](../../backend/coach/tests.py#L313))
  streams a usage chunk — with `tool_calls=None`.
- `test_tool_arguments_are_reassembled_across_chunks` ([`tests.py:596`](../../backend/coach/tests.py#L596))
  streams tool calls — with no usage chunk, and on `mock.Mock` chunks whose
  auto-created `.usage` yields no integers, so `_note_usage` returns before it can
  touch anything.

Both pass. The defect lives only in their intersection, which is the shape of every real
tool-calling turn. Thirty-two other tests stub `llm.stream_chat` wholesale, which is
right — but it means this function's body has exactly those two readers.

`ruff` does not flag it; the loop-variable-shadowing rules are not enabled.

Filed as **#290**.

### 2. `views.py` is the backend's `Masterji.tsx`

3,510 lines holding **24 view classes, 42 module-level helpers and 23 module-level
constants — 12 of them builder-visible prose**, with 793 comment lines among them. It is the file #270, #274, #276 and #287
all land in, which is the same sentence the frontend review wrote about `Masterji.tsx`
and the reason every parallel dispatch has to serialize.

The line count is not the finding. Three specific things inside it are:

**The judging seam lives in the view module.** `_react_to_proof` (149 lines),
`_react_to_declaration`, `_react_to_retirement`, `_labels_from_verdict`,
`_brief_from_proof` and `_brief_from_workshop` are the calls that build a judge prompt,
parse a verdict and decide what the gate will count — roughly 300 lines of the product's
actual reasoning, sitting between `MetricView` and `ChatView` because that is where they
were first written. `llm.py` is the transport, `gates.py` is the arithmetic, `bar.py` is
the vocabulary, and there is no module for the judgement. The absence is why
`_react_to_proof`'s docstring has to carry the whole design in prose: there is nowhere
else to put it.

**Coach-visible copy has two homes and no rule.** `guidance.py` holds `PHASE_HINT`,
`PROOF_HINT`, `PROOF_EXAMPLES`, `GATE_NUDGE`, `OPENERS` and `WORKSHOP_OPENERS`.
`views.py` holds `WELCOME`, the four `PHASE_BRIEF` entries, `TITLE_SHARPENED`,
`TITLE_LOCKED`, `OFFER_NO_DECLARATION`, `OFFER_DAY_CLOSED`, `OFFER_LANDED`,
`NOTES_LANDED`, `WORKSHOP_SPENT`, `REOPENED_SPENT` and `STREAM_BROKE` — every one of
them a sentence a builder reads. The split is historical, not principled, and it is the
kind that produces the drift this repo has already paid for: a reviewer asked to check
what the coach says has to know that half of it is in a file called `views`.

**Helpers that read the same rows several times per request.** `StateView` already holds
`goal`, then calls `_open_workshop(request.user)`, which re-runs `_active_goal` before
reaching `_reopened_workshop` — on the busiest authenticated endpoint in the product.
This is small (one indexed query) and is listed as an example of the shape rather than as
a performance finding; measuring the request's real query count was out of scope here and
is worth doing before anyone optimises anything.

The fix shape is the frontend review's, one layer down: lift the judging seam into its own
module, move the builder-facing strings to the module already named for them, and let the
views be the thin HTTP layer the rest of this codebase already is. Not a split by REST
resource — see what was deliberately not recommended.

Filed as **#292** (the judging seam) and **#293** (the copy).

## The rest, in short

**3. The workshop stream writes two events nobody reads, and one of them is wrong.**
`WorkshopChatView._events` yields `{"t": "sketch", ...}`
([`views.py:3149`](../../backend/coach/views.py#L3149)) and a `done` event carrying
`turns_used` / `turns_left` ([`views.py:3168`](../../backend/coach/views.py#L3168)).
`WorkshopEvents` in [`lib/coach-api.ts:1326`](../../lib/coach-api.ts#L1326) declares
`onDelta`, `onCandidates` and `onError` — and nothing else. Both events are dropped on
the floor; the client reads the sketch and the meter off the state refetch instead.

The `turns_left` it drops is also wrong. The line computes `WORKSHOP_TURNS - used`
against the constant 15, not against `_turn_budget(workshop)`, which is 5 in the
reopened room. Measured on a fresh reopened room after one turn: **the `done` event says
14 turns left; the state payload says 4**, and 4 is the number the server will refuse on.
The comment directly above it says the event exists *"so the meter and the server's own
refusal threshold are the same number"* — which is the one thing it does not do.

Nothing is visibly broken today, because nothing reads it. That is the finding: a wrong
number, under a comment asserting the invariant it breaks, in a place structurally
incapable of being noticed. `test_the_turns_left_the_client_shows_is_the_servers_own_count`
([`tests.py:6700`](../../backend/coach/tests.py#L6700)) is named for exactly this
invariant and only ever drives the 15-turn room. Filed as **#291**.

**4. 651 test methods across 90 classes in one 10,135-line file (#294).** `coach/tests.py` is
the largest file in the repository by a factor of three, and it is a known merge-conflict
domain — its tail collides on almost every rebase. The tests themselves are excellent
(see below); the container is the problem, and splitting it along the seams the classes
already imply is mechanical work that would take a real cost off every future session.

**5. 53 of the 88 coach migrations are changelog seeds the current rule forbids.** Of 56
`RunPython` migrations, 53 are `seed`/`unseed` pairs writing `ChangelogEntry` rows;
`coach/changelog/README.md` now says a changelog entry ships as a markdown file and
**never** as a data migration, and `load_changelog` is the command that replaced them.
The rule took hold — the three newest migrations are schema — so this is history rather
than drift, and it cannot be removed without squashing, which is not recommended below.
Recorded because 60% of the migration history being retired changelog seeds is a fact the
next person to read that directory will otherwise spend an hour deriving.

## What was checked and found good

Written down so the next reviewer does not re-derive it.

- **The gate is genuinely out of the model's reach.** `gates.py` is 351 lines, imports no
  LLM anything, and every path to a phase change goes through `try_advance`. `AdvanceView`
  and the chat's `propose_phase_advance` both land there; the tool call sets a boolean and
  nothing else. The product's central claim holds in the code.
- **`spend.py`'s never-raise discipline is exemplary, and `_live_actor` is the sharpest
  thing in the backend.** It exists because a dangling FK is checked at COMMIT rather than
  at INSERT, so an unchecked write would have rolled back the builder's own turn from
  inside the accounting that was added to protect it. That is a failure mode most
  codebases discover in production.
- **Tenancy is a filter everywhere, never a check afterwards.** Every pk-addressable view
  scopes its queryset by `request.user`, so a foreign id 404s with nothing to probe. I
  looked for the exception and did not find one.
- **The deterministic floor is real and consistent.** Every model call in the request path
  has a stock fallback, and `_react_to_proof`'s floor is `unjudged` rather than `accept` —
  the one choice here that costs the product something and is right anyway.
- **`Meta.ordering` does *not* corrupt VALIDATION's people-count, and I expected it to.**
  `CheckIn.Meta.ordering = ["-date"]`, and `gates.accepted_proofs` counts people with
  `rows.exclude(subject="").values("subject").distinct().count()` — the textbook shape for
  an inflated distinct count, since Django adds ordering columns to a `SELECT DISTINCT`.
  Measured on two accepted proofs about the same person on different dates: `.count()`
  returns **1**, correctly, because `count()` clears ordering before wrapping the query.
  Iterating the identical queryset returns **2**. So the code is right, and it is right by
  one line of Django's internals rather than by construction — an `.order_by()` on that
  queryset would make it right on purpose, and the day somebody iterates it instead of
  counting it, VALIDATION silently stops deduplicating people. Recorded rather than filed:
  nothing is broken, and the next reviewer will otherwise file it as a bug on inspection
  alone, as I nearly did.
- **The comment density is an asset and must survive any refactor.** Nearly every constant
  and branch records the failure that produced it. `_carried_over`'s docstring is the best
  example in the repository: it names the window, the timezones where it is generous, the
  builders it does not serve, and the test that pins the setting it depends on. **Any
  extraction must carry the comments with the code it moves** — the frontend review made
  this non-negotiable and it is more true here.
- **The two chat views are deliberately not unified, and the argument is correct.** The
  comment at [`views.py:2472-2487`](../../backend/coach/views.py#L2472) says a workshop
  turn and a coaching turn are not one thing, that the reopened room being handed no tools
  is the proof, and that only the parts where *a fix applied to one and not the other is
  the bug* were extracted. That is the right line and it was drawn in the right place.

## What was deliberately not recommended

- **Splitting `views.py` by REST resource.** Goals, check-ins, chat, cohorts as four
  modules would move the same code without addressing the thing that makes the file hard,
  which is that the judging seam and the coach's copy are in it. Lift those two out first
  and re-measure; the remainder may not need splitting at all.
- **A service layer, or fat models.** The helpers in this file are mostly pure functions
  over rows and they are already testable. Wrapping them in classes would add a layer and
  remove nothing.
- **Squashing the migration history.** 88 migrations on a months-old project is a lot, and
  squashing buys a faster test-database build in exchange for the one artifact that
  explains how the schema got here — on a product whose entire argument is an auditable
  record. Not worth it, and it would need coordinating across every live worktree.
- **A base class for `ChatView` and `WorkshopChatView`.** Covered above; the file's own
  argument against it is better than the one for it.
- **Component-level rewrites of `prompts.py`.** Out of scope and owned by the prose review.
- **Anything in `accounts/`.** #252–#255 are open and specific; a second opinion on them
  from a different lens would be noise.

## The order worth building in

1. **#290 — the `stream_chat` shadowing.** A two-line fix plus the test that would have
   caught it. Independent of everything, mergeable today, and it is silently skewing the
   one table #261's cost tripwire is meant to be read off.
2. **#291 — the workshop stream's dead events and wrong count.** Small, independent, and
   the decision (delete the events, or make the client read them) is worth writing down at
   the line rather than left for the next measurement to re-find.
3. **#292 — lift the judging seam out of `views.py`.** The largest of these and the one
   that unblocks the rest. Best done *after* #274/#276 land, for the same reason the
   frontend split waits on them: they rewrite the check-in path this touches.
4. **#293 — move the builder-facing copy into `guidance.py`.** Mechanical once #292 has
   settled the file's shape, and it must not be attempted in parallel with it.
5. **#294 — split `tests.py`.** Last, because it conflicts with everything above and is
   worth nothing until the code it tests has stopped moving.

## The index

| # | P | E | Title |
|---|---|---|---|
| [290](https://github.com/mahendra2890/masterji/issues/290) | now | S | A loop variable in `stream_chat` eats the tool call and the ledger row |
| [291](https://github.com/mahendra2890/masterji/issues/291) | next | S | The workshop stream writes two events nobody reads, and one of them is wrong |
| [292](https://github.com/mahendra2890/masterji/issues/292) | next | L | The judging seam lives in `views.py`, and there is no module for it |
| [293](https://github.com/mahendra2890/masterji/issues/293) | later | M | Coach-visible copy has two homes and no rule for which |
| [294](https://github.com/mahendra2890/masterji/issues/294) | later | M | 651 tests in one 10,135-line file |
