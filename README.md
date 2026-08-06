# Masterji — मास्टरजी

**The coach who makes you ship.** A tough-love AI execution coach for
first-time builders: one goal, earned phases, daily proof — no hiding in
planning.

Live at **[masterji.mscsoftwares.in](https://masterji.mscsoftwares.in)** ·
[Demo (no sign-in)](https://masterji.mscsoftwares.in/demo/)

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
  <!-- TODO before submission: N days of check-ins, link the screencast -->
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
  never breaks because an API flaked.
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
- **Hinglish toggle** — Masterji speaks natural Hindi-English if you want
  him to. ("Kaam dikhao, baatein nahi.")

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

No Google or OpenAI keys needed to explore: the login page grows a
**dev sign-in** button in development (the endpoint 404s in production),
and a failed LLM call degrades gracefully. Tests: `.venv/bin/python
manage.py test`.

Deployment (Vercel + Render + Neon + Namecheap DNS): see
[DEPLOY.md](DEPLOY.md).

## What exists vs. what's next

**Today:** the full coaching loop — goal, phases, gates, daily check-ins,
streaks, grounded chat, Hinglish, demo mode.

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
