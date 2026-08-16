# Screencast plan — the beats that have to be shown

The submission asks for a **10–30 minute** recording of the AI workflow. The
spine of that recording is [WORKFLOW.md](WORKFLOW.md), read in its own order:
the loop, the bill for running sessions in parallel, the times the model was
wrong, and what verification meant. Most of it is narration over an editor
and a terminal, and it does not need a shot list.

This file is the other four minutes — the moments that have to be *shown* on
screen rather than told, in the order they sit in the video, with how to
reproduce each one so nothing has to be faked or re-shot. Drop these into the
narration where they belong; they are not a running order for the whole video
and a four-minute video does not meet the brief.

Every clip below was run and observed on 10 August 2026 against a live model —
these are recordings of things that happened, not a storyboard of things that
should.

## What the video has to answer

The brief asks for three things. The video carries the first, and only glances
at the other two because the repo and the live URL already carry them.

1. **An AI workflow you can show** — which tools, in what order, the actual
   prompts, where it went wrong, what was verified. This is the whole video.
2. **A project someone can use** — one pass through the real app is enough;
   `masterji.mscsoftwares.in` and `/demo/` do the rest.
3. **A real impact angle** — one sentence at the top, then never again. The
   README carries the argument and the citations.

The failure mode to avoid: a product demo with the workflow bolted on at the
end. Lead with how it was built. The product is the evidence, not the subject.

## The shown beats — about four minutes of the recording

Timestamps are relative to this sequence, not to the finished video.

**0:00 · Who this is for.** One sentence, not a paragraph. A first-time builder
in a tier-2 college who has three notebooks of ideas and has never spoken to a
customer. Then the thesis in one more: *the judgement is borrowed, the
enforcement is the product.*

**0:20 · The loop.** The four steps from WORKFLOW.md, with the three prompts on
screen as text. Read the second one aloud — *"Make a list of all the action
items. In the decreasing order of priority based on the following: Product ·
User experience · use masterji with least friction"* — and say why the three
named axes are there: an unranked list of twenty findings is a way of doing
nothing.

Say the number of parallel sessions here (33 sessions in those six days, three
or four at once) and let it land before the next beat explains the bill.

**0:50 · The bill for parallelism.** The migration graph. Show
`backend/coach/migrations/` and count out loud: `0012` twice, `0015` **three
times**, `0018` twice, each stitched back by a merge migration. Then the fix,
which is the actual point — the rule went into persistent memory, so every
later session loads it before touching anything. *The real output of the
process is not the code, it's the constraints.*

**1:20 · Where the model was wrong — the cap.** The strongest twenty seconds
available. The agent proposed a `PUSHBACK_LIMIT` and a `CAPPED_ACCEPT`: after N
refusals, let the proof through. Clean code, sound reasoning, wrong product.
Say that out loud, then show that neither constant exists and what does:

```bash
grep -rn "PUSHBACK_LIMIT\|CAPPED_ACCEPT" backend/ ; echo "exit=$?"
```

Then run the test that replaced it, on camera. It submits four times and
asserts four push-backs and zero banked proofs, so no future session — yours or
the model's — can quietly put the cap back:

```bash
cd backend && .venv/bin/python manage.py test coach.tests.ProofRatchetTests.test_the_verdict_is_never_worn_down coach.tests.ProofStalemateTests -v 2
```

The test names carry the argument on their own, which is why this is worth
showing rather than describing — `test_a_stalemate_is_not_permission_to_pass`
and `test_the_fourth_look_has_to_diagnose_first` scroll past in the output.

**1:50 · …and the same refusal, from a real model.** Cut to the app. Four
submissions of "I plan to talk to them", four refusals, nothing banked. The
fourth reply is the one to read out:

> You still haven't brought the thing this phase asked for: one real reseller
> conversation tonight. "I'm going to message them" is another plan, not
> contact, so there's nothing here to validate yet. Stop rewriting the
> intention and bring back one person you actually talked to…

Firm, names what is missing, never insults them. Point at the gate: still
**0/3**.

**2:20 · Where the model was wrong — the opener.** The best story in the
project, because the AI-built product produced the bug and a transcript found
it. A builder tapped the app's own suggested question in IDEA — *"Who exactly
has this problem?"* — and got back *"You're asking the right thing, but not the
right week for stack or features."* Asked where they had mentioned either, it
said: *"You didn't. I'm correcting the drift before it starts."*

The phase's own central question, refused on a builder's first exchange, for a
topic nobody raised. Note the second-order cause on camera: the softening added
with `RESPECT_RULE` made this *more* likely, because a refusal that costs the
builder no face costs the model nothing to spend. **The fix is a condition, not
a gentler refusal** — show `ANSWER_WHAT_THEY_ASKED` in `prompts.py`.

Then tap the same opener live. Current answer:

> You already have the target: **Instagram resellers who handle around 10–30
> orders a week and lose track of who has paid**. Don't widen it to "sellers"
> or "online businesses"…

**2:50 · What verification meant.** Three claims, fast.

- ~1,860 browser calls — more time spent looking at the running app than
  writing files.
- The suite is hermetic, and that is checked rather than assumed. Run it with
  the provider pointed at a dead port, on camera:

  ```bash
  cd backend && OPENAI_BASE_URL=http://127.0.0.1:1 .venv/bin/python manage.py test
  ```

  All of them pass, in the same time as a normal run — 345 as of 13 August,
  and don't quote a number you haven't just watched print. Worth showing
  rather than asserting: a suite that stubs its model calls is easy to claim
  and easy to be wrong about, and one unstubbed call is all it takes to start
  costing money and failing offline.
- And the opposite check: nine scenarios run once against a live model, because
  a suite that stubs every model call proves the server and nothing about the
  coach.

**3:20 · The gate, in the product.** One pass, no narration needed beyond the
captions. Describe a real customer conversation in chat → Masterji writes the
proof up under Today → file it in one tap → **1/3**. Then ask him to advance
and watch the server refuse: *"Not yet. 0/3 accepted proofs in VALIDATION."*

**3:45 · Close.** The one thing a prompt could not do: the LLM has no
authority, the gate is a server-side state machine the model can only *propose*
an advance to. That design was not delegated, and it is exactly what the model
argued against when it proposed the cap. *The enforcement is the product.*

## Setup before recording

- Sign in as a throwaway account, not your own — your real record is the
  screenshot for the README, and you do not want a demo run in it.
- Have a goal already committed and the phase set to VALIDATION, so the
  conversation → draft → file beat starts immediately. Getting there honestly
  costs a whole IDEA cycle on camera.
- Two terminal tabs: one in `backend/` with the venv active for the test runs,
  one for `grep`.
- Editor open on `backend/coach/prompts.py` and `backend/coach/bar.py`.
- Browser at 1280×900 or larger. The dashboard is a two-column layout below
  that and the phone view is a different story than the one being told.
- Check the deployed app is awake before you start recording the product beats.

## What to leave out

- The architecture diagram. Nobody scores it and it costs thirty seconds.
- A feature tour. Thinking-partner mode is good work and belongs in the
  README, not in a four-minute video about how it was built.
- Anything you have not personally seen happen. Every beat above was observed;
  keep that property.

## The one thing the video cannot carry

- **`/demo/` first in the submission form**, ahead of the sign-in URL. Judges
  are time-boxed, and "see the real product, no account" removes the only
  friction between them and the gate refusing someone.

There were two. The other was a screenshot of your own Masterji record for the
credibility paragraph in the README, and that one is carried now:
`docs/run/the-record-at-launch.png` — reached LAUNCH, 7 proofs banked, 6 from
real-world contact. Say "where the ladder ended then" over it, the way the README
does: TRACTION was built after that run, and a shot captioned as the finish line
now stops one rung short of it. No reshoot — the caveat is what makes the real
screenshot honest.
