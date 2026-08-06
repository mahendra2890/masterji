# The corpus — everything Masterji knows

This folder is the coach's entire knowledge base: six small markdown
files. `prompts.py` assembles the system prompt per request from database
state plus the playbooks mapped to the builder's current phase
(`PLAYBOOKS_BY_PHASE`). There is no vector database and no retrieval
step — relevance is an editorial decision, made once, per phase.

That means you can read everything Masterji judges you on in about ten
minutes. This is a feature, not a gap. When the gate refuses you, the
reasoning traces to a sentence in this folder and a condition in
[gates.py](../gates.py) — not to an embedding's opinion.

## How a method earns its way in

1. **A human reads the source.** A book, an essay, a builder's public
   practice — read whole, not skimmed for quotes.
2. **They distill it in their own words.** Never reproduced text: this
   repo is public, and the coach must speak in one voice. If the
   distillation can't survive being rewritten from memory, it wasn't
   understood.
3. **They credit the source by name** in the playbook's header line.
   Borrowed authority is fine; hidden authority is not.
4. **They wire it to a phase** in `PLAYBOOKS_BY_PHASE`. A playbook that
   applies to every phase applies to none — pick the moment the advice
   is supposed to interrupt.

The bar for inclusion: would we say this sentence to a builder's face at
the moment the gate refuses them, and defend it when they push back?
Every line here has an accountable author.

## What stays out

- **Scraped content, tweets especially.** Indie-hacker Twitter is
  contradictory by construction — charge from day one vs. free until
  PMF, build in public vs. stealth — and survivorship-biased on top. A
  coach grounded on it stops having a spine. (It's also against X's
  terms, and republishing it here would be a copyright problem.)
- **Reproduced text of any source.** Credit by name; write your own
  sentences.
- **Advice at the wrong altitude.** Fundraising strategy, exit talk,
  scaling war stories — Masterji coaches the stretch from idea to first
  users, and the corpus stays inside it.

If a particular builder's method is genuinely worth encoding — see
[shipping-cadence.md](shipping-cadence.md) for the shape — it comes in
through the pipeline above, by hand.
