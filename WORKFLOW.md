# How this was built

Masterji was built in six days, between 5 and 10 August 2026, across 33 Claude
Code sessions — three or four of them running at the same time. This file is
the part of that which is worth keeping: the loop, the two failures that were
mine to fix rather than the model's, and what verification actually meant.

It is not a case for AI-assisted development. It's a record of where the
judgement stayed with me, because that turned out to be the only part that
mattered.

## The loop

Four steps, in this order, repeated maybe fifteen times.

**1. Ask for a review, not a feature.** The prompt that opened most sessions:

> *"pull latest, and do a thorough UI/UX review for masterji. What should I
> change, what will help users use the app better and more efficiently without
> dropping off?"*

No feature named, no solution proposed. The clause doing the work is *without
dropping off* — it's the metric I actually care about, so findings come back
ordered by it instead of by what's cheap to build.

**2. Force a ranking, on my axes.**

> *"Make a list of all the action items. In the decreasing order of priority
> based on the following: Product · User experience · use masterji with least
> friction"*

An unranked list of twenty findings is a way of doing nothing. Three named axes
turns it into P0/P1/P2, and puts the tie-breaks on my terms rather than the
model's sense of tidiness.

**3. Make it rate the work before doing the work.**

> *"Rate this requirement on product / future extensibility / usability / need
> for this feature in the product — I will use this to make the decision on
> whether to do it or drop it."*

The last clause is the whole thing. The rating is input to my decision, not
permission to start writing code. Several features died here, which is the
cheapest place for a feature to die.

**4. Fan out — one priority per session.** P0 in one session, P1 in another,
each in its own git worktree and branch, merged back through a pull request.
Nothing reached `main` unreviewed.

## Parallel sessions, and the failure they cause

Running several sessions at once is what made six days feel like three weeks.
It is also what broke the deploy three times, and the mechanism is worth
writing down because nothing about it is specific to this project.

Sessions share a working tree by default. Session A stages a file, session B
commits it, and now a pull request contains work nobody reviewed. The fix is
one branch and one worktree per session, and asking each one to prove it holds
nothing else before it pushes.

The subtler one was the migration graph. Two sessions each added a Django
migration and both numbered it `0012`. Each was independently correct. Together
they were two leaf nodes, and `migrate` refuses to guess — so `main` stopped
deploying.

It happened three times before the process changed, and it got worse before it
got better. The scar tissue is still in the tree, and you can count it:
`0012` twice, `0015` **three** times, `0018` twice, each rejoined by a
merge migration — `0014_merge_changelog_seeds`,
`0017_merge_four_session_changelogs`, `0019_merge_two_session_changelogs`.
A fourth commit belongs to the same family: `fa3e488 Renumber both
migrations onto main's leaf`, the cheaper version of the problem — one
session noticing that `main`'s leaf had moved under it and renumbering its
own two migrations rather than leaving a second leaf behind.

This is the characteristic bug of parallel agents: neither one is wrong, and
neither can see the other. Patching the migration doesn't help, because the
next set of sessions does it again — and as the `0015` case shows, the next
set can be bigger. What helped was writing the rule into
persistent memory — verify a single leaf before pushing and again before
merging — so every later session loads it before it touches anything. Most of
the durable rules in this project came from a failure exactly like that one,
and they are the real output of the process. Not the code; the constraints.

## Three times the model was wrong

**It graded its own homework.** VALIDATION asks for three things a customer
actually said. A builder gave three, in one sentence, and Masterji told him it
was "one usable line, not three." Nothing in the server could have known
better — the only thing that had read the answer was the model, reading its own
paragraph back and reporting a number. So the counting was taken away from it:
[backend/coach/bar.py](backend/coach/bar.py) holds each phase's bar as data,
builds the tool schema from that data, and computes the shortfall with a `len()`
and a subtraction. A model forced to emit a three-item array has nowhere left to
round three down to one, and *"1 more thing they said"* became arithmetic rather
than an opinion.

**It proposed a cap, and I killed it.** The suggestion was a `PUSHBACK_LIMIT`
and a `CAPPED_ACCEPT`: after N refusals, let the proof through. Clean code,
sound reasoning, wrong product — a coaching tool where persistence eventually
beats the gate has no product left. Neither constant exists in this codebase.
What exists instead is `test_the_verdict_is_never_worn_down` in
[backend/coach/tests.py](backend/coach/tests.py), which submits four times and
asserts four push-backs and zero banked proofs, so that no future session — mine
or the model's — can quietly reintroduce it.

The general shape: an agent optimises for the user not being stuck. Sometimes
being stuck is the product.

**It spoke in Masterji's voice when it had failed.** A reply that read as
hallucination turned out not to be a prompting problem at all — model *failures*
were being persisted as the coach speaking, so a flaked API call became a
message on the permanent record with Masterji's name on it. Two others in the
same family: a turn that produced only a tool call streamed nothing back at all,
and a summary that asserted a count of changes which, when asked where the
number came from, turned out not to have a source. That last one is a habit
rather than a fix — any number an agent hands you, ask what it counted.

## What verification meant

The agent has an in-editor browser it drives itself, and across the project it
used it about 1,860 times — click, run JavaScript, navigate, resize to 375px,
read the console, screenshot. More calls spent looking at the running app than
writing files. That ratio is the part I'd defend hardest: UI defects were caught
by the thing that made them, in the browser, minutes after the edit, instead of
by me an hour later.

Three other things carried weight:

- **Checks ran against production, not localhost.** The deployed app, the OAuth
  redirect, and — the one worth running yourself — that the development
  sign-in backdoor returns `404` in production.
- **The test suite is the ratchet.** ~200 tests pin the gate, tenancy (another
  user's ids `404`, not `403`), the one-goal database constraint, and the
  behaviour when the model is unreachable: the day is kept and the gate is not
  opened. That last one was itself a review finding, and a good example of the
  shape — the rule *a builder's streak shouldn't break when an API flakes* was
  right, and had been implemented as "accept the proof", which also banked it
  toward the next phase. One word was carrying two decisions, and with the
  model down a declaration of "think about the problem" could unlock
  VALIDATION. Splitting them is four lines; noticing was the work.
- **A public changelog row for every builder-visible change**, written in the
  same pull request that ships it. The product asks builders for evidence
  someone else can read; the repo owes them the same.

## The one thing a prompt couldn't do

The design that makes this product worth anything — that the LLM has no
authority, that gates are a server-side state machine the model can only
*propose* an advance to — was not something I could delegate, and it is exactly
what the model argued against when it proposed the cap. The enforcement is the
product. Everything above is how it got built without being talked out of
itself.
