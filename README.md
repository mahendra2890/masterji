# Masterji — मास्टरजी

**The coach who makes you ship.** A tough-love AI execution coach for
first-time builders: one goal, earned phases, daily proof — no hiding in
planning.

Live at **[masterji.mscsoftwares.in](https://masterji.mscsoftwares.in)** ·
[Guided tour (no sign-in)](https://masterji.mscsoftwares.in/demo/)

Built for the [bestpossible.ai](https://bestpossible.ai) Build Season 2026.

## Why

India has more aspiring founders than almost anywhere — the GUESSS India
2023 survey found **32.5% of college students are nascent entrepreneurs**
(vs 25.7% globally) — yet only **~4.8% of student ventures ever make
revenue**. The blunt, validation-first mentorship that closes this
intent-to-execution gap exists, but it's locked inside elite incubators.
The long tail of tier-2/3 builders gets courses, templates and toolkits —
consumption dressed as progress.

Masterji is not that mentor. It's the part of mentorship that can be
mechanised: a referee that refuses to discuss tech stacks until you've
talked to customers, demands proof of work every evening, and won't open
the next phase until the evidence is in. The judgment is borrowed. The
enforcement is the product.

## Who's holding the gate

A coaching product invites the obvious question: why trust this coach?

Not on my track record. I have not built something that thousands of
people use, and Masterji makes no claim to founder wisdom — be suspicious
of any tool that does. Its authority is procedural, and it rests on two
things you can audit:

- **The method is borrowed, in the open.** The gates encode *The Mom
  Test*, *The Lean Startup*, *MAKE* and Lean Canvas / JTBD — credited by
  name, distilled in my own words in
  [backend/coach/playbooks/](backend/coach/playbooks/) because this repo
  is public. A referee doesn't need to be a better player than the
  players. Every refusal Masterji makes traces to a condition you can
  read in [backend/coach/gates.py](backend/coach/gates.py) and a test
  that pins it.
- **The gates were pointed at me first.** I ran the rest of this
  hackathon through Masterji — one goal, declared each morning, proof
  each evening, phases I could not skip without editing my own database.
  What that loop produced is this repository — every builder-visible
  change between 5 and 10 August 2026 arriving through a reviewed pull
  request, and written to the product's own changelog on the way in. How
  it was built, and the three times the model was wrong about its own
  product, is in [WORKFLOW.md](WORKFLOW.md).
  That isn't a success story. It's a record, and it's the only kind of
  credibility a first build earns.

## How it works — the LLM has no authority here

The product's spine is a **server-enforced state machine**, not a prompt:

- **One active goal per user** — a database constraint, not a suggestion.
- **Phases:** `IDEA → VALIDATION → BUILD → LAUNCH`. Advancing requires N
  **accepted proofs** earned in the current phase (1 to leave IDEA, 3
  conversations to leave VALIDATION, 2 artifacts to leave BUILD). The
  check lives in [backend/coach/gates.py](backend/coach/gates.py) — the
  LLM can *propose* an advance via a function call; Django verifies
  against the database and refuses. You cannot jailbreak a `WHERE` clause.
  What that sentence does **not** cover is the row it counts: whether a
  proof becomes `ACCEPTED` is one model call over text the builder wrote
  themselves, which is the only place in this product where someone
  composes the input to a decision about them. So both judging prompts
  fence the submission and say that text inside it is evidence and never
  instructions — no line addressed to the model, no quoted "system"
  message, no verdict written out as though already reached, can move the
  verdict. An instruction found in there is worth nothing rather than worth
  a refusal: a pasted chat log carries all sorts of things, and a builder
  who did the work must not lose the evening to a paragraph they never
  wrote. The chat is deliberately *not* fenced — talking a coach into
  believing a customer said something is lying about the work, and no fence
  has ever fixed that.
- **A proof cannot be banked twice.** Several declare→prove cycles in a day
  are supported on purpose (real work counts when it happens), and each
  accepted proof banks toward the phase — so one conversation filed three
  times in an evening used to clear VALIDATION, the phase whose entire job
  is preventing that. The judge could not have known: it was shown tonight's
  refused tries on that one row and nothing further back. Now the same words
  twice is refused in server code with no model in the loop (arithmetic, not
  a judgement), and the goal's already-accepted proofs go into the evening
  prompt so a conversation *retold* is caught too. Between those two sat a
  third road, and it was the one the product had just made easiest: Masterji
  writes tonight's proof out of the conversation, and a complete draft filed
  unedited is accepted without a model call — so Tuesday's conversation
  described again tonight came back as *his* words, which the exact-match
  check cannot recognise, on a path no judge ever reads. The draft is where
  that has to stop, because the draft is where it is decided, so the record
  now travels with the instruction not to write one of them up a second time.
  None of the three refuses a second
  real piece of work, a second conversation the same evening, or the next
  step on the same artifact — a gate that fails in that direction is worse
  than the hole it closed.
- **The daily loop:** declare one task every morning, submit proof every
  evening. A lenient LLM pass reacts (accept / push back) — and if the model
  is unreachable the proof is filed `UNJUDGED`, which is neither verdict:
  the day counts everywhere days are counted (the record, the streak — those
  read a declaration and a proof, never a verdict) and it banks nothing
  toward the phase, so the cycle stays open and filing again once the model
  answers gets that evening a real reading. The loop surviving an outage was
  always right; banking a gate proof on the same word was a second decision
  riding along, and it handed the gate to whoever caught the model on a bad
  afternoon. A resubmission is judged against every
  try that was refused *and the words that refused each one*, so the second
  look can't invent a reason the first didn't give. Past `STALEMATE_AT`
  refusals the prompt stops asking for a verdict and asks for a diagnosis
  first — *is the work missing, or is the work there and the two of you
  failing to understand each other?* — because those two failures produce an
  identical stack of push-backs and only one of them is the builder's. The
  second case is the coach's to fix: accept, and write the proof out as he
  now reads it. It is deliberately **not** a cap. Nothing passes because a
  builder resubmitted often enough; work that isn't there is refused on the
  fourth try and the fortieth.
- **Masterji drafts the proof, the builder files it.** The commonest way to
  lose an evening was to describe real work in chat, get coached at about
  it, and file nothing — because translating what you said into what the
  box wanted was your job. Now the coach reads the conversation against the
  phase's bar and calls `suggest_proof` with tonight's proof written up in
  the builder's own words. It lands on the check-in as a draft. Filed
  unedited it skips a second judgement (he decided when he offered);
  edited, it's judged with his own draft in the prompt. The offer records
  nothing by itself: filing is the builder's, and so is the gate credit.
  Evidence is judged on what it *contains*, never on reproducing the
  playbooks' format — nobody is tested on how well they learned our
  vocabulary.
- **He writes it down as you say it, so you never say it twice.** He used to
  hold every piece in his head until the bar was fully met, which meant
  nothing accumulated anywhere and every turn re-derived the evening from a
  transcript — the mechanism behind the loudest complaint this product has
  had: *it keeps asking for things I already gave it*. The draft is now a
  running record (`CheckIn.proof_offer`), rewritten as each piece arrives and
  paired with what the bar still lacks (`CheckIn.proof_missing`). The builder
  sees both under **Today**; the next chat turn and the evening's judgement
  both read the notes as facts already given, so nothing in them can be asked
  for a second time.
- **And what the days before produced.** All of that was scoped to one
  evening. The record of every earlier day reached no prompt at all, so on the
  fourth evening of VALIDATION the coach had the count — *2/3 accepted proofs
  toward BUILD* — and not one word of what was in the 2, and would send a
  builder back to the person they interviewed on Tuesday. The goal's accepted
  proofs now travel with the phase and the streak as facts from the database:
  what they said, what was declared, which phase stamped it. Not scoped to the
  current phase, deliberately — a conversation had while still in IDEA is a
  conversation they had, and re-asking for it because the row carries the
  wrong label is the failure being fixed. `gates.py` still counts the rows and
  has still never read a prompt.
- **The counting is the server's, not the model's.** VALIDATION asks for
  three things the customer said, and the failure that started this was a
  builder giving three in one sentence and being told *"that's one usable
  line, not three."* Nothing in the server could have known better: the only
  thing that had read that answer was the model reading its own paragraph
  back. So `suggest_proof` stopped taking a paragraph plus the model's verdict
  on it and started taking **the parts** —
  [backend/coach/bar.py](backend/coach/bar.py) holds each phase's bar as data,
  builds the tool schema from it, and computes what is still owed with a
  `len()` and a subtraction. A model that must emit `["…", "…", "…"]` has
  nowhere left to round three down to one, and *"1 more thing they said"* is
  arithmetic rather than an opinion. It buys no leniency either way:
  `proof_missing` is what separates notes from an offer, only a draft with
  nothing missing files straight through without a second judgement, filing a
  short one is still judged on its merits, and `gates.py` counts what it
  always counted.
- **Phase-gated coaching:** the system prompt is assembled per-request
  from database state plus the phase's playbook — small, self-authored
  distillations of the lean-execution canon (crediting *The Mom Test*,
  *The Lean Startup* and *MAKE* by name) in
  [backend/coach/playbooks/](backend/coach/playbooks/). No vector DB:
  relevance is decided by the phase, so retrieval is a dict lookup. The
  corpus is deliberately small enough to read in ten minutes; how a
  method earns its way in — and why scraped tweets never will — is
  written down in the
  [curation policy](backend/coach/playbooks/README.md).
- **Two ways of talking, both the builder's to set.** *Hinglish* — Masterji
  speaks natural Hindi-English if you want him to ("Kaam dikhao, baatein
  nahi"). *Thinking partner* — for the work that comes before there's
  anything to declare, he switches to questions and options instead of
  assignments. Both live on the user, not the turn. The mode sits over the
  composer as two options with the live one lit, rather than as one button
  naming the mode you already have — a control that states its own state
  tells nobody that the other one exists. Neither is a way past the gate:
  `gates.py` doesn't read either field, and a test pins it.

## Architecture

```
Browser ──► Next.js 16 (Vercel) ── /api/* rewrite ──► Django 5 + DRF (Render, Docker)
                                                        │  litellm → openai/gpt-5.4-mini
                                                        │  (switch = one env string)
                                                        ▼
                                                     Neon Postgres
```

- **Auth:** Google OAuth (authorization-code flow) → simplejwt in httpOnly
  cookies, kept first-party by the same-origin `/api/*` proxy.
- **LLM seam:** [backend/coach/llm.py](backend/coach/llm.py) is ~50 lines
  over [litellm](https://github.com/BerriAI/litellm). Provider optionality
  is the `LLM_MODEL` env var (`openai/gpt-5.4-mini` today,
  `anthropic/claude-sonnet-5` tomorrow). Keys live server-side only.
- **Talking and judging are not the same call.** `LLM_JUDGE_MODEL` serves the
  two that decide something recorded on the row — the evening's
  accept / push-back, and the morning's on-phase reading plus the tailored
  `proof_ask` the evening is then graded against. A weak turn of conversation
  is a weak turn of conversation; a wrong verdict either banks a proof that
  isn't there or sends a builder who did the work away to rewrite it, and the
  second one is how this product loses people. It is also where instruction-
  following is under the most load: those prompts carry the bar, the substance
  rule, the prior tries, the stalemate diagnosis, the banked record and the
  evidence fence, and every failure in this product's own bug history is a rule
  that was in the prompt and didn't land. `LLM_VISION_MODEL` chains off the
  judge rather than the chat model, because the only call that ever sends an
  image is that same evening verdict — so upgrading the judge cannot leave half
  a verdict behind on the cheap model. Both default to `LLM_MODEL`: unset, the
  ladder collapses to one model and behaviour is identical. Upgrading the judge
  does **not** mean switching provider — the step to reach for is the non-mini
  sibling of whatever `LLM_MODEL` names (`openai/gpt-5.4` against today's
  default), so it is one env var and the key you already have.
  There is a third road to an `ACCEPTED` row and it is worth naming rather than
  leaving inside that word "two": a complete draft filed unedited is accepted in
  server code with no model call at all, and the decision behind it was the
  **chat** model's, made when `suggest_proof` wrote it. What the server checks
  there is arithmetic — every part of the phase's bar present, and a list long
  enough ([bar.py](backend/coach/bar.py)) — never the substance. That is the
  deliberate price of the one-tap file: asking the judge to re-open a draft
  Masterji offered himself can only produce a disagreement with himself, and the
  builder is the one who would pay for it. An edited draft, and every other
  proof, goes to the judge.
- **Observability:** loguru for domain events; optional OpenTelemetry
  tracing (`coach.turn` span per interaction with phase/model/gate
  attributes) — a no-op unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- **Soft delete everywhere**, tenancy by queryset (foreign ids 404).
- **Tests:** `backend/coach/tests.py` — the gate, tenancy, the
  one-goal constraint, and the LLM-down fallback are all pinned.

## Run it locally

```sh
# backend (Python 3.13 + uv)
cd backend && uv sync && .venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 8000

# frontend
npm install && npm run dev
```

No Google or OpenAI keys needed to explore: the sign-in popup grows
a **dev sign-in** button in development (the endpoint 404s in production),
and a failed LLM call degrades gracefully. Tests: `.venv/bin/python
manage.py test`.

Deployment (Vercel + Render + Neon + Namecheap DNS): see
[DEPLOY.md](DEPLOY.md).

## What exists vs. what's next

**Today:** the full coaching loop — goal, phases, gates, daily check-ins,
streaks, grounded chat, Hinglish, thinking-partner mode, screenshot proofs
graded by a vision model in the same call as the text (`LLM_VISION_MODEL`,
inlined as a data URL so a private record never gets a fetchable link), and a
four-step guided tour of the real screens that needs no sign-in — starting
where a builder actually starts, on the goal-commit screen and the first
morning in IDEA. What has moved since
the first build is in the product itself — **What's new** in the header opens
the changelog, served from the `ChangelogEntry` table (public endpoint, so the
tour reads it too) and written from the admin rather than from a deploy.

**Phase 2 (Product Month):** Telegram-bot channel · missed check-in
nudges · pgvector memory over past check-ins · citation-per-refusal (every
pushback names the playbook and `gates.py` condition that grounded it) ·
₹99–199/mo via UPI (free for students) · incubator/E-Cell dashboards.

**vs. the field:** Overlord (YC) enforces generic habits at $12.99/mo;
Pre (YC S24) coaches funded US founders. Neither encodes a lean-startup
state machine behind validation evidence, and neither is priced or
voiced for India.

## License

MIT
