# Idea and product review — 21 August 2026

A snapshot, not a maintained document. It reviews `main` at `324de37`, two days
before an investor/incubator conversation. Nothing here is load-bearing for the
claims in [README.md](../../README.md) — if the two disagree, the README is the
product and this is an opinion about it.

Produced by running two skills from [gstack](https://github.com/garrytan/gstack)
against this repository: `office-hours` (startup mode — six forcing questions,
premise challenge, forced alternatives) and `plan-ceo-review` (HOLD SCOPE, over
the 48-hour plan that came out of the first). The skills were read from a clone
and executed by hand; gstack is not installed on this machine, so none of its
persistence, telemetry or brain-context steps ran.

## What the diagnostic found

Four answers, given by the builder, in his own ranking:

| Question | Answer |
|---|---|
| Q1 · Demand reality | One builder who is not him used it once, real work, no return |
| Q5 · Observation | That builder **argued with the coach** instead of doing the work |
| Q4 · First payer | Nobody yet, and he would say so in the meeting |
| Q3, Q2, Q6 | Skipped — the README already answers them, specifically |

### The finding that outranks the meeting

The architecture is built to defeat **jailbreaking**: the gate is a `WHERE`
clause, `gates.py` never reads a prompt, and
`test_the_verdict_is_never_worn_down` pins that four refusals bank nothing. The
model once proposed a `PUSHBACK_LIMIT` with a `CAPPED_ACCEPT` and was
overruled, correctly — that history is in [WORKFLOW.md](../../WORKFLOW.md).

What was observed is not jailbreaking. **The gate held and the builder was lost
anyway**, because arguing with the coach felt like working on the startup. The
README's promise is "no hiding in planning". This is a third hiding place —
*hiding in arguing* — and the deliberate no-cap decision makes it free and
unbounded by design.

Stated as the rule: **a refusal that engages is a refusal that rewards.**

The shape of a fix is not a cap on acceptance — that was the model's error, and
it is still wrong. It is a cap on the *transaction*: past `STALEMATE_AT`
([prompts.py:1063](../../backend/coach/prompts.py)) the coach stops negotiating
and ends the evening. Nothing passes that did not pass before; the conversation
simply stops being somewhere an evening can be spent. This is **not** in the
48-hour plan, and it should not be — see "NOT in scope".

### The contradiction an investor finds in thirty seconds

The roadmap reads `₹99–199/mo via UPI (free for students)`. The ICP is a
student. So the stated business model excludes the stated user.

The resolution already exists in the code: `cohorts.py` and the four routes in
[urls.py](../../backend/coach/urls.py) are an institutional product, shipped,
with the sharpest competitive sentence in the repository sitting in its
docstring — NEC and NSRCEL cohorts rank on jury-judged self-reports, *"so the
loudest deck wins, and this board has no field a deck can be written in."*
The student surface is how the rows get written. The board is what somebody
buys.

## The premises

Accepted without objection:

1. The gate works and is not the problem. No further gate work buys anything.
2. The bottleneck is evidence, not product. 356 merged pull requests, 3 open
   issues, and `loop_report` has never been pointed at production.
3. The payer is institutional whatever the roadmap says.
4. "They argued with the coach" is a product finding, not a bug report.

## The plan — approach A, narrated as C

Zero code. Recruit real builders, watch unassisted, measure with the instrument
that already exists, and reframe the pitch around the buyer who actually pays.

The reason is the product's own: **VALIDATION counts people, not evenings.**
There is one person and a great many evenings. `gates.py` would print `1/3`.

### Hour by hour

```
  HOUR 0     Point loop_report at production. Record the baseline before
             anybody is recruited, so the after-number has a before.
  HOUR 1-2   Recruit. E-Cell WhatsApp groups, Build Season Discord, own
             college. The ask is one evening, not a signup.
  HOUR 3-20  They use it. Unassisted, unwatched, no hand-holding — a guided
             pass produces nothing Q5 can read.
  HOUR 21    loop_report again. The delta is the demand slide.
  HOUR 22-24 Seed one real cohort in Django admin (there is deliberately no
             route for creating one) and put the real rows on the board.
  HOUR 25+   Rewrite the opening two minutes around the ledger, not the coach.
```

### Failure modes registry

| Failure | Visible how | Mitigation |
|---|---|---|
| Nobody shows up | `loop_report` delta is zero | Recruit 4x the target; the ask is one evening, not a product |
| The numbers are bad | They are bad in public | A measured bad number beats an unmeasured story; say what it is |
| Ten strangers arrive the same evening on free-tier Render | First-touch latency, cold start | Stagger the ask, or warm the instance before the window opens |
| Sign-in blocks them | Dev sign-in 404s in production, by design | Google OAuth is the only door; test it from a phone on mobile data first |
| `loop_report` run against prod with a local branch | Nothing — it is read-only | Verified: no `save`/`create`/`update`/`delete`/`get_or_create` in the command, and it calls only `gates`/`streaks` read helpers. A grep cannot rule out a write inside a helper; the docstrings claim none and the helpers are read-only by inspection |
| `DATABASE_URL` for prod lands in shell history | It does not announce itself | Export from a file, do not paste the URL inline |

### Threat model, briefly

The one new risk this plan creates is **reading real builders' rows**.
`loop_report` prints counts, not text — no proof bodies, no goal titles, no
messages — which is what makes it safe to read out loud, and it is the same
discipline `cohorts.py` holds. Anything screenshotted for the meeting should
come off the counted surfaces for that reason. Prior screenshot work found 24
of 40 captures had unrelated browser tabs in frame; crop before publishing.

## NOT in scope

- **Closing the arguing hole.** The best finding of this review, and the wrong
  work for the next 48 hours: it touches `prompts.py`, the most load-bearing
  and most-regressed path in the product, two days before a demo. It is a
  post-meeting issue, and it deserves its own `office-hours` session.
- Any of the three open issues (#321, #277, #261).
- Monetization surface. "Nobody yet" is a defensible answer; a half-built
  paywall is not.
- New product. The 357th pull request adds to a pile that is already too tall
  for the argument it is being asked to make.

## Sections not run, and why

`plan-ceo-review`'s eleven-section deep review assumes a code plan. Over a
zero-code plan, Architecture, Error & Rescue Map, Code Quality, Test Review,
Performance, and Design & UX have nothing to read. Run: Temporal
Interrogation (0E), Security & Threat Model, Observability, Deployment &
Rollout, Long-Term Trajectory. Skipped sections are named rather than
performed, because a review that reports on sections it could not see is worse
than one that admits the gap.

## The assignment

Before the meeting: **five real builders through one unassisted evening each,
and `loop_report` run against production twice** — once before, once after.
Walk in with the delta.
