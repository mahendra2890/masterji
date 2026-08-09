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
  What that loop produced is this repository — every builder-visible change
  between 5 and 10 August 2026 arriving through a reviewed pull request, and
  written to the product's own changelog on the way in.
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
- **The daily loop:** declare one task every morning, submit proof every
  evening. A lenient LLM pass reacts (accept / push back) — and if the
  model is down, the proof is accepted with a stock reaction: the loop
  never breaks because an API flaked. A resubmission is judged against every
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
streaks, grounded chat, Hinglish, thinking-partner mode, and a four-step
guided tour of the real screens that needs no sign-in — starting where a
builder actually starts, on the goal-commit screen and the first morning in
IDEA. What has moved since
the first build is in the product itself — **What's new** in the header opens
the changelog, served from the `ChangelogEntry` table (public endpoint, so the
tour reads it too) and written from the admin rather than from a deploy.

**Phase 2 (Product Month):** Telegram-bot channel · missed check-in
nudges · pgvector memory over past check-ins · screenshot proofs with
VLM grading · citation-per-refusal (every pushback names the playbook
and `gates.py` condition that grounded it) · ₹99–199/mo via UPI (free
for students) · incubator/E-Cell dashboards.

**vs. the field:** Overlord (YC) enforces generic habits at $12.99/mo;
Pre (YC S24) coaches funded US founders. Neither encodes a lean-startup
state machine behind validation evidence, and neither is priced or
voiced for India.

## License

MIT
