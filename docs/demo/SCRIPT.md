# Masterji — the demo, end to end

The **narration**, written to be spoken. Every claim is checkable against this
repository; every screenshot it calls for is in [`docs/run/`](../run/), and all
seventeen are bundled as one slide-per-image PDF at
[`masterji-screens.pdf`](masterji-screens.pdf) so a video generator can use the
real product rather than inventing pictures of it.

**Three lengths, one script.** Read straight through, the unmarked text runs
**about thirteen minutes** (a little over 1,900 words at a normal pace) — that's
the one to record. Sections marked **`[+ OPTIONAL]`** are self-contained
expansions; add all four and it runs **about seventeen**. For a **~10-minute**
cut, drop the four passages marked `[10-MIN CUT]` — about 300 words, none of
them load-bearing, which lands at about eleven minutes at a measured pace and a
shade over ten read briskly. Every version is inside the 10–30 minute brief.

Timestamps on the headings are for the thirteen-minute read.

The video's job is the **workflow**, not the product. The product appears only as
evidence for a claim about how it was built.

---

## 0:00 · It refuses me

> **Slide 1** — `the-gate-refuses.png`

That's my own product refusing me. Two of three customer conversations banked,
and it will not open the next phase. Nothing I type talks it out of that, because
the refusal isn't a personality — it's a `WHERE` clause in a Django query.

Masterji is a tough-love execution coach for first-time builders. One goal, five
phases — from writing the problem down to a stranger coming back or paying:
declare one task every morning, file proof every evening, and a phase does not
open until the evidence is banked. No idea yet? A turn-metered workshop sits
under the commit box, and the only door out of it is committing to one.

It's for a nineteen-year-old in a tier-two Indian college with three notebooks of
ideas who has never spoken to a customer. Thirty-two and a half percent of Indian
college students are nascent entrepreneurs; about four point eight percent of
student ventures ever make revenue. The mentor who closes that gap is the one who
says *we're not discussing your tech stack until you've talked to somebody* — and
that mentor mostly lives inside elite incubators.

That's the last I'll say about the product as a product. The rest is how it got
built.

## 1:10 · The loop

Six days to the POC, the fifth to the tenth of August. A hundred and fifty-two
commits. Fifty-seven reviewed pull requests. Thirty-three Claude Code sessions,
three or four at a time. Every number here belongs to those six days; the work
has carried on since, and the loop was four steps that never changed.

**One: I never asked what to build. I asked for a review.** *"Pull latest, and do
a thorough UI/UX review. What should I change, what will help users use the app
better without dropping off?"* No feature named, no solution proposed. The clause
doing the work is *without dropping off* — that's the number I care about, so
findings come back ordered by it instead of by what's cheap.

**Two: force a ranking, on my axes.** *"List all the action items in decreasing
priority based on product, user experience, and using Masterji with least
friction."* An unranked list of twenty findings is a way of doing nothing. Three
named axes turns it into P0, P1, P2, and puts the tie-breaks on my terms.

**Three: make it rate the work before doing the work.** *"Rate this requirement
on product, extensibility, usability, need — I will use this to decide whether to
do it or drop it."* That last clause is the trick. The rating is input to my
decision, not permission to start coding. Features died there, which is the
cheapest place for a feature to die.

**Four: fan out.** P0 in one session, P1 in another, each in its own git worktree
and branch, merged back through a pull request.

## 2:55 · What running four agents at once costs

That's what made six days feel like three weeks. It's also what broke my deploy,
three times.

`[10-MIN CUT: drop this paragraph]`
Sessions share a working tree by default — session A stages a file, session B
commits it, and a pull request now contains work nobody reviewed. So every session
gets one branch, one worktree, and has to prove it holds nothing else.

The subtler one is still sitting in this repository. Count duplicate migration
numbers on `main`: `0012` twice, `0015` three times, `0018` twice. Two sessions
each added a migration and both numbered it `0012` — independently correct,
together fatal. Two leaf nodes, and `migrate` refuses to guess, so `main` stopped
deploying. Look at the middle one: `0015` had *three* sessions collide.

That's the characteristic bug of parallel agents — neither is wrong, and neither
can see the other. Patching the migration doesn't help; the next set does it
again, and the next set can be bigger. What helped was writing the rule into
persistent memory: verify a single leaf before pushing, and again before merging.
**The real output of the process isn't the code. It's the constraints.**

## 4:15 · The first time the model was wrong: it offered me a way out

The agent proposed two constants — a pushback limit and a capped accept. After N
refusals, let the proof through. Clean code, sound reasoning, completely wrong
product: a coaching tool where persistence eventually beats the gate has no
product left.

What I wrote back was *"the trade-off you should veto if you disagree — I
disagree. Don't make it pass anyway."*

Neither constant exists in this codebase. What exists instead is a test called
`test_the_verdict_is_never_worn_down`, which submits four times and asserts four
push-backs and zero banked proofs — so no future session, mine or the model's,
can quietly put the cap back.

> **Slides 2–3** — `model-talk-not-user-proof.png`, `the-tries-that-were-refused.png`

`[10-MIN CUT: drop this paragraph, and Slides 2–3 with it]`
And the refusals aren't a stock reply; each names a different failure. *"That's
model talk, not user proof."* *"You answered the tone change, but you ignored
half the ask."* Every refused try stays on the record with the words that refused
it, so the next attempt is judged against all of them and the second look can't
invent a reason the first didn't give. That proof was accepted on the third try —
because the work arrived, not because it was third.

**An agent optimises for the user not being stuck. Sometimes being stuck is the
product.** That judgement I couldn't delegate.

## 5:40 · The other edge of the same line

So I killed the cap and kept the refusals. Which raises the obvious problem: what
happens when a nineteen-year-old in placement season types something that isn't
about the work at all?

A coach whose only move is *name what you're avoiding and do the smallest real
thing next* gives that answer to *"my parents want me to stop wasting time on
this"* too. It's the wrong answer delivered with total confidence. And nothing in
my prompt file drew that line — I searched it for exhaustion, for being pushed to
stop, for wanting out, and got nothing back.

> **Slide 4** — `some-nights-are-not-about-the-work.png`

Three messages, three replies.

*"I can't do this."* — "Then stop for tonight. If you mean *I want to stop this*,
that's allowed today; the goal can be closed with no penalty."

*"This is too tough."* — "Yes, it is tough. Keep it small: one real person, one
real question, ten minutes. If tonight is a no, say *stop this goal* and I'll
treat it as a decision, not a failure."

*"I want to give up."* — "You can stop this goal today; that is a valid choice
and it costs nothing. If you mean you're in real trouble or might hurt yourself,
this is past what I can handle here — tell a person you trust, or a doctor, right
now."

Three things make that a rule rather than a mood. **There's no task underneath
any of those replies**, and the gate still reads one of three in the same frame —
nothing banks because a night was hard, and nothing is taken away. **It only
fires when the builder raises it**, because deciding somebody is struggling from
a gap in their record is inventing it. And **he stays a coach** — no counsellor
voice, no diagnosis, and never a helpline number a model half remembers.

Hard on the work, easy on the person. Same line as the cap, from the other side.

## 8:00 · The third time: it counted its own paragraph

VALIDATION asks for three things a customer actually said. A builder gave three,
in one sentence, and was told it was *"one usable line, not three."*

Nothing in the server could have known better — the only thing that had read that
answer was the model, reading its own paragraph back and reporting a number. The
prompt that caught it was mine: *"he counted sentences, not items — is this not
being done by AI?"*

So the counting left the model. `bar.py` holds each phase's bar as data, builds
the tool schema from that data, and computes what's owed with a `len()` and a
subtraction. A model that has to emit a three-item array has nowhere left to
round three down to one.

> **Slide 5** — `the-counting-is-the-servers.png`

*"That's the commitment ask. I still need whether he said yes or no."* Every
piece is acknowledged as it lands, and the shortfall is named. **"One more thing
they said" is arithmetic, not an opinion.**

## 9:05 · What verifying it meant

The test suite is hermetic, and that's checked rather than assumed. Every test
stubs the model, and the base case stubs it to *raise*, so the suite exercises
the deterministic floor unless a test says otherwise. That's easy to claim and
easy to be wrong about — one unstubbed call and it quietly starts costing money
and failing on a train. So it's verified the only way it can be: the whole suite
runs with the provider pointed at a dead port. **Three hundred and forty-five
tests on the thirteenth of August, all passing, in the same time as a normal
run.** A single real call would have hung.

`[10-MIN CUT: drop this paragraph]`
Then the opposite check, because a stubbed suite proves the server and nothing
about the coach: nine scenarios driven end to end against a live model with no
mocks. One was itself a review finding, and it's the shape of the whole project.
The rule *a builder's streak shouldn't break when an API flakes* was right, and
had been implemented as "accept the proof" — which also banked it toward the next
phase. One word carrying two decisions, and with the model down, "think about the
problem" could unlock VALIDATION. Splitting them was four lines. Noticing was the
work.

## 10:35 · One run, and the recursion at the end of it

> **Slides 6–9** — `the-bar-is-met-stop-grinding.png`, `the-phase-unlocks.png`,
> `build-is-earned.png`, `a-screenshot-as-proof.png`

I ran the whole loop on the finished product. The moment I'd point at first: I
kept talking past what was needed, and it said *"Stop. You already gave enough to
clear the bar — and you also slipped back into names when I asked for the
route."* **It refuses to grind for more than the bar asks**, which is only
possible because the bar is data on the server rather than a mood.

`[10-MIN CUT: shorten to just the last sentence]`
At two of three it added something I didn't build for that moment: *"Abhinav
already counts, so the next one must be a different person, or a different, new
conversation with him about a new step."* The same proof cannot be banked twice.
Three of three: *"Earned. BUILD is yours to open."* Earned, not granted.

Now look at what my BUILD proof actually was. The task I declared was *improve
tone and tighten the scope of the coach*, and the proof I filed was the
before-and-after of Masterji's own prompt: from *"be very strict and direct"* to
*"be very strict and direct, yet respectful — understand that the person at the
other end is human and can make mistakes."* That change came from real user
feedback. Too harsh. Too pushy. Doesn't help unblock.

So I used Masterji to hold myself to fixing Masterji's tone — and it graded the
fix and told me the evidence was thin: *"this lands, but you still missed the
example on one identical builder input that I asked for."* It was right.

And the gate didn't move an inch for any of it. `gates.py` doesn't read the tone
setting, the language setting, or the thinking-partner setting, and there are
tests pinning that. **Soften the voice, never the gate.**

> **Slide 10** — `the-record-at-launch.png`

Reached LAUNCH. Seven proofs banked, six from real-world contact, five days of
work on the record — where the ladder ended then. TRACTION was built after that
run, so the finish line has moved further out since. That's not a success story.
It's a record, and it's the only kind of credibility a first build earns.

The design that makes this worth anything — that the LLM has no authority, that
the gate is a state machine the model can only *propose* an advance to — is
exactly what the model argued against when it offered me the cap. That one I had
to hold myself.

**The judgement is borrowed. The enforcement is the product.**

*— end of the core script —*

---

# `[+ OPTIONAL]` expansions

Each is self-contained. Drop them in at the marked place; all four together take
the run time to about eighteen minutes.

## `[+ OPTIONAL A]` The second time the model was wrong — insert after "the other edge of the same line" (~1:30)

My favourite failure in the project, because the AI-built product produced the
bug and a transcript found it.

A builder tapped the app's *own* suggested opening question in IDEA — *"Who
exactly has this problem?"* — and got back: *"You're asking the right thing, but
not the right week for stack or features."* Asked where they'd mentioned either,
it said: *"You didn't. I'm correcting the drift before it starts."*

The phase's own central question, refused on a builder's first exchange, for a
topic nobody raised. And the second-order cause is the interesting part: the
softening I'd added — the rule telling it to be respectful — made this *more*
likely, because a refusal that costs the builder no face costs the model nothing
to spend.

The fix is a condition, not a gentler refusal: a block in `prompts.py` called
`ANSWER_WHAT_THEY_ASKED`, conditioned on the builder actually raising the thing
being corrected — the same guard as the rule above.

> **Slide** — `a-solution-is-not-a-problem-statement.png`

Here's the refusal that condition protects, still working: *"No. You gave me a
solution, not the problem statement. 'Coach' and 'steps' wait for BUILD."* That
one is correct, because he really did propose a solution. The bug was refusing
when they hadn't.

## `[+ OPTIONAL B]` The browser did the verifying — insert at the top of "what verifying it meant" (~0:40)

First, the agent verified in a real browser rather than in a description of one:
about **eighteen hundred and sixty** browser-driving calls across the project —
click, run JavaScript, navigate, resize to three hundred and seventy-five pixels,
read the console. More calls spent looking at the running app than writing files.

> **Slide** — `filing-on-a-phone.png`

That's the check-in on a phone, caught by the thing that made it.

## `[+ OPTIONAL C]` The fuller run — insert at the top of "one run" (~1:40)

I declared *finalise the problem statement* and got refused: *"Not enough. This
phase is not just the problem statement; it's the problem statement plus the
route to where these people already are."*

> **Slides** — `the-first-refusal-and-the-draft.png`,
> `the-notes-and-what-is-missing.png`, `off-phase-and-a-worked-example.png`,
> `claim-the-win.png`

It wrote the proof up from the conversation, I filed it, and it was accepted:
*"that's the one I pulled out of our conversation, so there's nothing left for me
to argue with."* IDEA closed; VALIDATION opened with three questions belonging to
*that* phase.

In VALIDATION the notes accumulate as you talk, with a box underneath headed
*still needed tonight*. That exists because the commonest way to lose an evening
was doing the work, describing it in chat, and filing nothing — translating what
you said into what the box wanted was your job. Now the coach writes it up.
Filing is still yours, and so is the gate credit.

One refusal in BUILD is worth watching: the work was real but aimed at the wrong
phase — BUILD wants the smallest thing a user can touch, so rewriting the coach's
own prompt is tooling rather than exposure. Next to that refusal the app will
unfold a proof that *was* accepted, so the bar is something you can read instead
of guess at.

## `[+ OPTIONAL D]` Who's holding the gate — insert before the final line (~0:40)

I won't claim founder wisdom — I haven't built something thousands of people use,
and you should be suspicious of any coaching tool that says otherwise. The method
is borrowed and credited in the open: *The Mom Test*, *The Lean Startup*, *MAKE*,
distilled in `backend/coach/playbooks/`, in a public repo. A referee doesn't have
to be a better player than the players.

---

## Slide index

All seventeen are in [`docs/run/`](../run/) and bundled in
[`masterji-screens.pdf`](masterji-screens.pdf), one per page, captioned.

| # | File | What it shows |
|---|---|---|
| 1 | `the-gate-refuses.png` | 2/3 in VALIDATION; advance refused; the same person can't count twice |
| 2 | `model-talk-not-user-proof.png` | *"that's model talk, not user proof"* |
| 3 | `the-tries-that-were-refused.png` | accepted on the third try, both refusals unfolded in red |
| 4 | `some-nights-are-not-about-the-work.png` | three replies, no task under any of them |
| 5 | `the-counting-is-the-servers.png` | the shortfall named as arithmetic |
| 6 | `the-bar-is-met-stop-grinding.png` | *"Stop. You already gave enough to clear the bar"* |
| 7 | `the-phase-unlocks.png` | accepted, IDEA → VALIDATION, streak, phase-specific openers |
| 8 | `build-is-earned.png` | 3/3 — *"Earned. BUILD is yours to open."* |
| 9 | `a-screenshot-as-proof.png` | a real WhatsApp thread filed as BUILD evidence |
| 10 | `the-record-at-launch.png` | reached LAUNCH · 7 proofs · 6 from real contact · 5 days — LAUNCH was the last rung then |
| 11 | `a-solution-is-not-a-problem-statement.png` | *"you gave me a solution, not the problem statement"* |
| 12 | `filing-on-a-phone.png` | the check-in on a 375px viewport |
| 13 | `the-first-refusal-and-the-draft.png` | first declaration refused, running notes, drafted proof |
| 14 | `the-notes-and-what-is-missing.png` | what he has so far, and *still needed tonight* |
| 15 | `off-phase-and-a-worked-example.png` | off-phase refusal beside an accepted example |
| 16 | `the-draft-lands-under-today.png` | the draft on the check-in form, still to be filed |
| 17 | `claim-the-win.png` | *"Earned. Proof is on the record."* |

Raw URL pattern once this is on `main`:

```
https://raw.githubusercontent.com/mahendra2890/masterji/main/docs/run/<file>
```

---

## Driving a video generator from this repo

**Sources to add, in this order:**

1. **[`masterji-screens.pdf`](masterji-screens.pdf)** — add this *first*. It is
   seventeen pages, one real screenshot each, captioned. This is what makes the
   video show the product instead of stock illustrations.
2. **This file** (`docs/demo/SCRIPT.md`) — the running order and the words.
3. [`../../WORKFLOW.md`](../../WORKFLOW.md) — long-form version of the same
   argument; deepens the middle sections.
4. [`../../README.md`](../../README.md) — the impact figures and citations.

Where sources disagree on emphasis, **this file wins** — it's the one written to
be spoken.

**Customisation prompt to paste in** (this is the part that controls the
visuals):

```
Use the seventeen screenshots in masterji-screens.pdf as the primary visuals.
More than half of all on-screen time must be these real product screenshots —
prefer them over generated illustrations, stock imagery, icons or abstract
graphics, and never invent a picture of the product. Follow SCRIPT.md as the
running order and show the slide it names at each beat, holding each screenshot
long enough to read the highlighted text. Target ten minutes; keep the four
optional sections out. Lead with how the product was built — it is a workflow
story, not a product tour. Keep every failure: the migration collisions, the
capped-accept the AI proposed and I rejected, and the counting bug. Do not
smooth these into a success story and do not make it sound like an
advertisement.
```

**Then check two things before you upload the result:**

- **Run time.** The submission needs 10–30 minutes. If the generator returns
  something much shorter, add the optional sections and regenerate rather than
  submitting a five-minute cut.
- **The image ratio you asked for.** Skim the output and count: if generated
  visuals outnumber the seventeen screenshots, re-run with the PDF placed first
  and the customisation prompt restated. A generator that hasn't ingested the
  PDF will fall back to inventing pictures, and that is the failure mode to
  watch for.
