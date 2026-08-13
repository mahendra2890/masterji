# Tech and flow review — 14 August 2026

A snapshot, not a maintained document. It reviews `main` at `a2446fc`, and like its
predecessor it is meant to age: as the issues below close, this becomes a record of what was
thought on one day. Nothing here is load-bearing for the claims in
[README.md](../../README.md) — if the two ever disagree, the README is the product and this is
an opinion about it.

It follows [the 13 August product review](2026-08-13-product-review.md), whose 39 proposals
(#60–#98) have mostly landed: TRACTION, the Workshop, the people-and-kinds gate, throttles,
link checking, export, CI. Everything below is **new relative to that backlog**. Where an open
issue already covers a finding, this review endorses or reprioritises it rather than refiling
it.

The 22 proposals live as GitHub issues **#145–#166**, each carrying the mechanism, the files it
lands in, and a priority and effort label. What is written here is the part that does not
survive being cut into 22 pieces.

## How it was produced, and what that is worth

Three read-only exploration agents over the real tree — the phase machine and its models, the
playbook corpus and the coach, and the engineering surface — then one pass by hand over what
they returned. Not the five-lens panel that produced the August 13 document, and not
thesis-guarded the way the pre-idea lens was there.

Two limits worth stating:

- **Every factual claim below was re-read against the files before it was written down, and
  the two that could only be settled by running were run.** `manage.py test coach.tests` runs
  371 tests; `manage.py test` runs 380. 57 of the 74 migrations in `coach` are changelog data
  seeds. Both numbers are load-bearing for findings 1 and 2, and neither is an estimate.
- **The engineering half is a code review, not a load test.** No profiler was run, no query
  plan was read, and the production database was not touched. Findings about cost — the
  presign count, the thread arithmetic, the missing indexes — are read off the code and the
  configuration, and each one names what it would take to confirm.

## The three findings that lead

**1. The auth test suite has never run in CI, and the workflow says why by accident.**
[`.github/workflows/checks.yml:62`](../../.github/workflows/checks.yml) runs
`manage.py test coach.tests`. `backend/accounts/tests.py` holds nine tests that no pull request
and no push to `main` has ever executed. They are not incidental coverage: they pin a dead
cookie returning 401 rather than 500, a token for an unknown user, an expired access cookie
reading as *signed out* rather than *broken* — one of them is introduced in the file as *"the
bug this class exists to prevent, in the three shapes that"* it took. A regression in any of
them signs every builder out and presents as an outage.

The workflow's own header is the argument for fixing it: *"Nothing here is a new rule. Every
command below is one a session is already instructed to run before it pushes."* The instruction
is the unqualified command; the label is drift, and the full suite is **faster** (86s against
94s) because the qualified one still pays for the same database. It is one word (#145).

**2. Content lives in migrations, and that is the leaf collision — not bad luck.** 57 of the
74 `coach` migrations are `ChangelogEntry` data seeds. The README says the changelog is
*"written from the admin rather than from a deploy"*; the tree says otherwise. Combine that
with the house rule that every builder-visible change ships a changelog row in the same pull
request, and **every substantive PR writes a migration** — so two parallel sessions collide on
the leaf essentially every time.

This repo has already built a tool to detect that collision, and
[`check_migration_leaf`](../../backend/coach/management/commands/check_migration_leaf.py)'s own
docstring records that a second leaf broke main's deploy three times. It is a good tool aimed
at a self-inflicted wound. Moving entries to a versioned data file loaded idempotently at boot
returns migrations to being schema, and the renumber-on-rebase loop disappears for every PR
that changes no schema — which is most of them (#149).

**3. There is not one index in the project, and soft delete multiplies the cost.**
`grep -rn "db_index\|models.Index\|Meta.indexes"` over `backend` returns zero. Only Django's
implicit foreign-key indexes and the three conditional `UniqueConstraint`s exist.

The two that matter are the two the product's own design created.
[`gates._banked`](../../backend/coach/gates.py) filters `CheckIn` on `goal`, `phase` and
`proof_status` — the gate's own query, run on every state load, every chat turn during prompt
assembly, and every advance — and two of those three columns are unindexed. And
`SoftDeleteModel` puts `deleted_at IS NULL` on *every query of every model* through the default
manager, so the house-wide soft delete quietly makes the missing index a house-wide cost. None
of it is visible at today's row counts, which is the argument for landing it now: the first
person to feel it will be the builder with the longest record (#146).

## The engineering findings, in short

Beyond the three above, in the order they are worth doing.

- **No `transaction.atomic` anywhere in the backend** (#147). Three multi-write paths run
  unwrapped, and one of them is
  [`gates.try_advance`](../../backend/coach/gates.py) — `goal.save()` then
  `PhaseTransition.objects.create()`. A failure between those two statements advances a phase
  and writes no transition row. In a product whose entire claim is that the record is
  trustworthy because the server wrote it, that is a record quietly disagreeing with itself,
  and nothing would ever detect it.
- **`_offer_target` runs twice on every chat turn** (#148) — `views.py:1512` and `:1551`, the
  same query, no write between them.
- **Up to 90 presigns per dashboard load** (#150). `CheckInSerializer.get_proof_image_url`
  signs one URL per row and `StateView` serializes `CHECKIN_HISTORY = 90`. Invisible only
  because R2 is optional: this is a latency cliff that appears the day storage is switched on,
  on the screen every builder opens first, and it will read as *the app got slow*.
- **A provider wobble takes the whole app down** (#151). One worker, twelve threads, every
  model call inline; a single `prove` can hold its thread for ~180s of retries and timeouts.
  The product degrades correctly *per call* — `UNJUDGED` exists exactly for this — but not per
  *service*, so during an outage every request pays full timeout before reaching the graceful
  path. A wall-clock budget and a short-lived breaker fix it without a queue.
- **No token or cost accounting** (#152). litellm returns usage on every response and nothing
  records it. Three questions have no answer: what a builder costs against the planned
  ₹99–199/mo, which prompt is expensive, and whether an account is abusive — throttles cap
  requests, so an 8,000-character turn and a 40-character one are identical against
  `chat: 30/hour`.
- **The one public endpoint has no ceiling** (#153). `ChangelogView` is `AllowAny` with no
  throttle scope and an ad-hoc `?limit=` that returns the whole table on an unparseable value.
- **`ChatView` and `WorkshopChatView` are the same 200 lines twice** (#154), mirrored again on
  the client. Filed as a prediction rather than a complaint: this is where the next divergence
  bug comes from, and the tree already contains a comment warning that a third copy of a string
  lives in TSX and *"is the one to check when this wording changes."*

Three things were checked and found already settled, so nothing was filed:
`CorpusCurationTests` already pins that every playbook is wired to exactly one phase, credits
its source on line 2, and leaves no orphan file; `links.py` hardens SSRF properly, with the
residual DNS-rebinding hole knowingly filed as #136; and the health check's never touching the
database is intentional — a liveness probe that fails when Neon does is a liveness probe that
restarts the wrong process.

Two existing issues are endorsed unchanged rather than restated: **#130** (ruff is a declared
dev dependency that nothing runs, and its config is `select = ["I", "F401"]`) and **#117** (no
frontend harness — `app/Masterji.tsx` is 2,461 lines and one component, against a backend
decomposed into eight modules).

## The ladder stays at five

The August 13 review recorded *"Do not let the ladder grow past five phases."* TRACTION then
took the fifth slot. That decision holds, and it was re-examined rather than assumed: the only
sixth rung that survives the altitude rule is a SCOPE phase between VALIDATION and BUILD, and
it is worth naming in order to refuse it — SCOPE is desk work placed immediately after the
phase that finally got the builder talking to people, which is the exact hiding place the
ladder exists to prevent.

So "more steps" is answered with steps that are **not rungs**. There are three shapes of them,
and one structural gap underneath all three.

**The gap first, because it is the largest single finding in this review.** `Goal` is `title`
+ `phase` + `status` + timestamps. Nothing in the product *is* the idea. The four things
[`bar.BAR[Phase.IDEA]`](../../backend/coach/bar.py) collects — the problem, the place, why
those people, the first conversation — land in a `CheckIn.proof_parts` blob on one row and are
never promoted anywhere. Three consequences, and they run through everything else this review
was asked about:

- **Nothing to revise.** `title` is the only thing a builder can sharpen, which is why "the
  idea is never ready" has nowhere to land after the commit: the idea is a 200-character
  string.
- **Nothing to carry.** #63 has to reconstruct the parent idea from accepted proofs, because
  no field holds it.
- **Nothing for the coach to point at.** Every other fact in `build_system_prompt` is a
  database row. The idea itself is a headline.

`Goal.brief` (#155) closes it, and it is cheap because none of the extraction is new —
`bar.labels` already does this work for the evening draft and is reused unchanged.

The steps themselves: **a phase-entry commitment** (#156), one line at each unlock naming what
this phase will produce, stored on the `PhaseTransition` row that already exists and carries
only from/to today — a beat at every transition that costs no ladder length; **intra-phase
beats** (#157), so that VALIDATION's first conversation and its third stop being identical to
the server, computed from the banked count with no model in the loop; and sideways,
**pivot without amnesia** (#63), raised to `now` because the commonest real journey event for
this builder is the idea dying while the problem survives, and today the honest move costs more
than limping on.

## The corpus, and the gate standing on an empty shelf

The August 13 review found VALIDATION to be *"the heaviest gate standing on the thinnest
shelf"*, and #66 and #67 were the answer. That same argument now applies to a bar that shipped
**after** that review was written, and it is the strongest corpus finding here.

[`gates.PROOFS_REQUIRED[Phase.BUILD]`](../../backend/coach/gates.py) is
`Need(n=2, kinds={"touched": 1})` — a hard condition: nobody leaves BUILD without evidence a
real user touched the thing. BUILD's three playbooks are `over-engineering`, `mvp-scoping` and
`shipping-cadence`. A field guide to the smells, how to cut scope, and how to ship daily. All
three teach *building*; not one teaches getting a person in front of it. The phase refuses on a
condition the corpus never taught. `first-users.md` does teach recruiting by hand — and it is
wired to TRACTION, two phases too late to help anyone stuck at that gate (#158).

The other three, in order of the hole they fill:

- **Coming Back**, wired to TRACTION (#159). The terminal phase carries **one** playbook, and
  `first-users.md` teaches acquisition. `bar.BAR[TRACTION]` asks for a return *or* a payment;
  nothing in the corpus teaches retention, and `the-first-rupee.md` is wired to LAUNCH, so a
  builder chasing either half of that bar has already left the playbook for it. This is the
  phase the README's opening statistic is actually about, and it is the least-resourced one in
  the product.
- **Talking to People You Know**, wired to VALIDATION (#160). The gate now counts distinct
  people, which made *who* the first three are load-bearing in a way it was not when this
  corpus was written — and for a first-time builder anywhere they are friends, classmates and
  flatmates, because those are the people who say yes to someone with nothing to show.
  `customer-conversations.md` names the bias in its source's title and never works through the
  case.
- **The Narrow First User**, wired to IDEA (#162). `bar.py` insists that a channel *"is not a
  room and does not count"*, and both `place` and `why_there` are downstream of a segment most
  builders have never cut.

One is filed deliberately as an **amendment rather than a new file**: the second idea, into
`over-engineering.md` (#161). One active goal is a database constraint with no method behind
it — when the shinier idea arrives mid-BUILD, and it always does, the product's entire answer
is a `UniqueConstraint` refusing to create a second goal. That is enforcement with no coaching
under it, which is the one shape this product says it is not. It goes in as an amendment
because `over-engineering.md` is already the field guide to the smells and this is one of them,
and because BUILD cannot afford a fifth file in its prompt when #158 already takes it to four
and **nothing in the repo measures assembled prompt size** (#152, again).

Endorsed unchanged: **#69** reading-the-nos, **#70** writing-the-post, **#72** the
thirty-minute-slice amendment.

Every new playbook must satisfy `CorpusCurationTests` — one phase, source on line 2, no orphan
file — and the source has to be one a human has actually read whole. The issues name the slot
and the moves and leave the attribution open, because
[the curation policy](../../backend/coach/playbooks/README.md) requires a reader, not a
citation.

## The idea is never ready

The Workshop (#77) shipped and it is good: fifteen turns, at most three parked candidates,
`suggest_goal` filling the commit box and committing nothing. What follows is what it still
does not do — and the pattern is that all four are about the boundary, not the room.

**The workshop's thinking dies at the commit line** (#163), and this is the product's own
loudest recorded complaint reproduced one screen later. The README describes the mechanism
behind *"it keeps asking for things I already gave it"* and the fix built for it: a running
draft that later readers treat as facts already given, *"so nothing in them can be asked for a
second time."* That fix is scoped to one evening inside one goal. Fifteen turns of workshop are
the same problem across the commit line — the builder has just established the problem, who has
it and where those people are, and IDEA's bar then asks for the problem, who has it, one
specific place they already are, and why they think so. The same four things. Only
`suggested_title` survives.

**Rehearse the bar before committing** (#80, raised from `later` to `now`). This is the most
direct answer the backlog holds, because it is the one that makes *ready* stop being a feeling:
four countable parts, with the count computed by `bar.read()`'s subtraction rather than
asserted by a model. Its stated dependency — the Workshop — has shipped, so the reason it was
sequenced behind is gone. It should be built with #163 and #155: all three are the same four
bar parts, rehearsed before the commit, carried through it, kept afterwards. Together they are
one idea; apart they extract the same parts three times.

**The two candidates you did not pick die with the workshop** (#165). The tiebreak produces one
winner and two survivors, and the survivors are discarded at the moment they become useful — a
builder whose idea dies on day 4 must retire the goal to reach a room, and finds it empty when
they get there. The cap is not the thing to relax; three is the mechanism. What is wrong is
that the other two die for no reason.

**And there is no room after the commit at all** (#166), which is where the doubt actually
lands. The workshop is available only while no goal is active — the deliberate inverse of the
"Set a goal first" guard. So day-0 doubt gets a room and day-4 doubt gets
`WHEN_THEY_DOUBT_THE_IDEA` inside a chat still carrying the phase rules and the daily loop: a
coach who has to keep pushing the loop while being asked whether the loop is pointed at the
right thing. Thinking-partner mode changes which side of the table he sits on and explicitly
does not change the phase rules, which is correct and is not this. The alternative available
today is to retire the goal to get a room back — and the product should not make burying the
idea the cheapest route to reconsidering it. A bounded reopening, ~5 turns, once per goal,
whose three exits are keep going, sharpen, or pivot.

**A fourth opener** (#164). `WORKSHOP_OPENERS` says of its three that they *"are the actual
freezes, not three flavours of 'help me brainstorm'"*. It is one short: *"someone's already
built this"* is a different freeze from *"is my idea too obvious"* — obvious is a fear about
the idea's worth, competition is a belief that the question is settled. It is also the one most
likely to be wrong in a way the coach can address, and the answer is already this product's own
thesis.

## The order worth building in

**Now** — the one-word CI fix (#145) and the indexes (#146), because both are cheap and both
get worse with time; atomicity (#147) and the double query (#148); the two playbooks whose
gates are already refusing people (#158, #160); the pre-idea trio that should land together
(#163, #80, and #155 immediately behind them); the fourth opener (#164); and the pivot (#63).

**Next** — the changelog out of migrations (#149), which is the one that repays itself on every
subsequent pull request; the operational set (#150, #151, #152, #153); ruff (#130); deletion
(#86); then the structural product work — phase-entry commitments (#156), the surviving
candidates (#165), the room after commit (#166) — and the remaining corpus (#159, #161, #69,
#70, #95).

**Later** — the streaming dedup (#154), the frontend harness (#117), intra-phase beats (#157),
the narrow first user (#162), #72.

A note the issues cannot carry: **#163, #80 and #155 are one piece of work in three tickets.**
All three handle `bar.BAR[Phase.IDEA]`'s four parts — rehearsed before the commit, carried
across it, kept on the goal afterwards. Built in one pass they share an extraction that already
exists. Built separately, each will grow its own.

## What was deliberately not recommended

The most losable content in any review, because an issue tracker has no way to record a
decision *not* to build something.

- **No sixth rung.** SCOPE between VALIDATION and BUILD is the only candidate that survives the
  altitude rule, and it is desk work placed immediately after the phase that finally got the
  builder talking to people. The phase-entry commitment (#156) buys most of its value for one
  line and no rung.
- **No pre-commit errand.** "Go stand in that queue before you commit" lengthens the stretch
  before real-world contact, which is what the ladder exists to shorten, and it turns the
  workshop into the phase it was carefully built not to be.
- **No scoring or ranking of parked candidates.** `Workshop.candidates` is bare strings on
  purpose, and the model comment says why: a candidate that can carry a score is a candidate
  you can research instead of test. #165 carries them further without letting them grow.
- **No async job queue for the LLM calls.** #151 is real, but a queue is a second service on a
  workspace whose free instance-hours are already the binding constraint
  ([DEPLOY.md](../../DEPLOY.md) §6). A wall-clock budget and a breaker buy most of the
  protection for none of the hosting cost.
- **No vector store over the corpus.** Ten playbooks, readable in ten minutes. The dict lookup
  is the feature, and the curation policy argues it better than an issue would.
- **No splitting of IDEA or VALIDATION, and no weekly retrospective ritual.** Both were refused
  on 13 August and both refusals still hold. Restated here rather than left to age out of view
  with the older document.

## The index

Priority and effort as labelled on each issue.

### Engineering
| # | P | E | Title |
|---|---|---|---|
| [145](https://github.com/mahendra2890/masterji/issues/145) | now | S | The auth test suite has never run in CI |
| [146](https://github.com/mahendra2890/masterji/issues/146) | now | S | There is not one index in the project |
| [147](https://github.com/mahendra2890/masterji/issues/147) | now | S | No `transaction.atomic` — `try_advance` can lose the transition row |
| [148](https://github.com/mahendra2890/masterji/issues/148) | now | S | `_offer_target` runs twice on every chat turn |
| [149](https://github.com/mahendra2890/masterji/issues/149) | next | M | Content lives in migrations — 57 of 74 are changelog seeds |
| [150](https://github.com/mahendra2890/masterji/issues/150) | next | S | Up to 90 presigns on every dashboard load |
| [151](https://github.com/mahendra2890/masterji/issues/151) | next | M | A provider wobble takes the whole app down |
| [152](https://github.com/mahendra2890/masterji/issues/152) | next | S | No token or cost accounting anywhere |
| [153](https://github.com/mahendra2890/masterji/issues/153) | next | S | The one public endpoint has no ceiling |
| [154](https://github.com/mahendra2890/masterji/issues/154) | later | M | `ChatView` and `WorkshopChatView` are the same 200 lines twice |

### Journey and flow
| # | P | E | Title |
|---|---|---|---|
| [155](https://github.com/mahendra2890/masterji/issues/155) | next | M | The Goal has no body — the idea is a 200-character string |
| [156](https://github.com/mahendra2890/masterji/issues/156) | next | M | Phase-entry commitment: name what this phase will produce |
| [157](https://github.com/mahendra2890/masterji/issues/157) | later | M | Intra-phase beats: conversation 1 and conversation 3 differ |

### Playbook corpus
| # | P | E | Title |
|---|---|---|---|
| [158](https://github.com/mahendra2890/masterji/issues/158) | now | S | The First Touch — BUILD's gate demands it and nothing teaches it |
| [160](https://github.com/mahendra2890/masterji/issues/160) | now | S | Talking to People You Know — now that the gate counts people |
| [159](https://github.com/mahendra2890/masterji/issues/159) | next | S | Coming Back — the terminal phase teaches only acquisition |
| [161](https://github.com/mahendra2890/masterji/issues/161) | next | S | Amendment: the second idea (`over-engineering.md`) |
| [162](https://github.com/mahendra2890/masterji/issues/162) | later | S | The Narrow First User — making IDEA's `place` answerable |

### Pre-idea coaching
| # | P | E | Title |
|---|---|---|---|
| [163](https://github.com/mahendra2890/masterji/issues/163) | now | M | The workshop's thinking dies at the commit boundary |
| [164](https://github.com/mahendra2890/masterji/issues/164) | now | S | A fourth opener: "someone's already built this" |
| [165](https://github.com/mahendra2890/masterji/issues/165) | next | S | The two candidates you didn't pick die with the workshop |
| [166](https://github.com/mahendra2890/masterji/issues/166) | next | M | There is no room after commit, and that is where doubt lands |

### Reprioritised or amended, not refiled
| # | Change |
|---|---|
| [80](https://github.com/mahendra2890/masterji/issues/80) | later → **now**. Its dependency (the Workshop) shipped; build with #163 and #155. |
| [63](https://github.com/mahendra2890/masterji/issues/63) | next → **now**. `PREDECESSOR_BLOCK` simplifies to "carry the parent's brief" if #155 lands first. |
| [86](https://github.com/mahendra2890/masterji/issues/86) | Amended: `CheckIn.subject` is a **third party's** name, and soft delete means erasure does not currently reach it. |
| [130](https://github.com/mahendra2890/masterji/issues/130), [117](https://github.com/mahendra2890/masterji/issues/117), [136](https://github.com/mahendra2890/masterji/issues/136), [116](https://github.com/mahendra2890/masterji/issues/116) | Endorsed unchanged — this review reached the same findings independently. |
