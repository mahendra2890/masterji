# Product review — 13 August 2026

A snapshot, not a maintained document. It reviews `main` at `6d0f4ed`, and it
is meant to age: as the issues below close, this file becomes a record of what
was thought on one day rather than a description of the product. Nothing here
is load-bearing for the claims in [README.md](../../README.md) — if the two
ever disagree, the README is the product and this is an opinion about it.

The 39 proposals live as GitHub issues **#60–#98**, each carrying the full
mechanism, the files it lands in, and a priority and effort label. What is
written here is the part that does not survive being cut into 39 pieces: why
these three findings lead, what order to build in, and — the most losable
thing in any review — the things that were deliberately **not** recommended.

## How it was produced, and what that is worth

Five reviewers, one lens each: the phase ladder, the playbook corpus, the
pre-idea moment, functional robustness, and the competitive field. Each read
the real repository rather than a description of it, and every proposal was
required to name the files it touches — a proposal that cannot name its
landing site is usually a proposal that has not been thought through.

Two honest limits on the result:

- Each lens was then checked by a **thesis guardian** whose only job was to
  refuse anything that quietly dissolves the product — gate weakening,
  content-library creep, wrong altitude, a second active goal. Only the
  pre-idea lens got that pass; the other four died on a session limit, and
  their proposals were checked by hand against the same list. The pre-idea
  verdicts are recorded in the issues themselves (seven keep, one modify).
- The competitive lens researched comparators on the open web. Its claims
  about Overlord, Pre, buildspace, YC Startup School, NEC and NSRCEL carry
  URLs in the issues and were not independently re-verified here.

## The three findings that lead

**1. The product abandons the builder at its own climax.** LAUNCH is terminal,
and because [`at_finish_line()`](../../backend/coach/gates.py) counts
`accepted_proofs_total`, "Claim the win" lights the moment LAUNCH opens —
before a single public post, on the strength of proofs that already paid for
the BUILD exit. The button is meant to be the database talking about LAUNCH;
it is talking about BUILD. Meanwhile the statistic the README opens with —
~4.8% of student ventures ever making revenue — describes the stretch that
begins exactly where the ladder ends. Fixing the button is one line (#61);
giving the builder somewhere to go afterwards is TRACTION (#60).

**2. The coach is structurally absent at the moment builders freeze.**
`ChatView`, `DeclareView` and `ProveView` all refuse with "Set a goal first."
when there is no active goal, so a builder's first contact with Masterji is
the welcome message written *after* the commit that frightens them.
Thinking-partner mode is billed as serving "the work that comes before there's
anything to declare," but it only alters the chat prompt inside an existing
goal. The commit screen — the one place the product has to answer "my idea
isn't ready" — is the one screen where it cannot speak. That is the whole of
the "the idea is never ready" problem, and #77 is the substantial answer to
it, with #73, #75 and #76 as the cheap ones that need no new machinery.

**3. VALIDATION is the heaviest gate standing on the thinnest shelf.** It
demands three proofs — more than any other phase — and carries one playbook,
while BUILD demands two and carries three. The two hardest moves in the whole
arc for the target builder are uncovered by the corpus: getting a stranger to
agree to talk to you (#66), and asking a real person for money (#67). The
second is doubly strange, because a stranger's payment is already a countable
proof part in [`bar.py`](../../backend/coach/bar.py) and
`launch-checklist.md` already asserts that "a ₹99 payment tells the truth"
without teaching a single method for extracting one.

## The order worth building in

**Now** — small, and mostly independent of each other. The one-line finish-line
fix (#61); the night-owl rule (#81), which today refuses a proof filed at 00:30
against last night's declaration and breaks the streak for it — the product
punishing precisely the evening it exists to capture; draft persistence (#82),
because a phone discards background tabs and an evening's proof is a paragraph
typed on a phone keyboard; throttles (#83), which must exist before payments
make free-tier abuse economics real; the commit-screen repricing (#73) and the
idea-doubt register (#75); and the two VALIDATION-shelf playbooks (#66, #67).

**Next** — the structural work. TRACTION (#60) is large and touches the
hardcoded ladder in `Landing.tsx` and `Tour.tsx` as well as the backend. The
Workshop (#77) with its mining (#78) and parking lot (#79). The two gate
sharpenings — counting people rather than conversations (#91), and counting
kinds rather than rows (#62). Then the record work: weekly recap (#84), export
(#85), deletion (#86), PWA (#87).

**Later** — everything else, including the pieces that only pay off once
TRACTION exists.

A note on sequencing that the issues cannot carry: **#91 and #62 are the two
that most repay being done early**, despite being labelled `next`. Both move a
promise the product already makes in prose into a `WHERE` clause. The README
tells the reader that "the person already counted cannot be counted again" —
today that promise is kept only by the judge prompt, and the entire product
thesis is that prompts are what cannot be trusted with the gate.

## What was deliberately not recommended

The most losable content in any review, because an issue tracker has no way to
record a decision *not* to build something. Each of these was considered and
turned down:

- **Do not split IDEA or VALIDATION into finer phases.** Their bars are
  already multi-part in `bar.py`; splitting them only lengthens the stretch
  before a builder makes real-world contact, which is the failure the whole
  ladder exists to prevent. #62 buys the rigour a split would buy, by counting
  which parts of the bar a proof satisfied, at zero added ladder length.
- **Do not add a weekly retrospective ritual.** A retro that does not
  terminate in contact is journaling, and journaling is the respectable form
  of hiding this product was built to refuse. #84 and #95 are deliberately the
  opposite shape: the week *read back* from rows the server already holds,
  never a form asking the builder to self-report.
- **Do not adopt money stakes.** Beeminder's pledge ladder is a real
  commitment device and it is wrong here — unaffordable for the target builder
  and hostile to their payment rails. The equivalent stake for #93 is paid in
  record, not rupees: a visible slip trail rather than a charge.
- **Do not follow the field into self-reported milestones.** NEC and NSRCEL
  cohorts run on jury-judged decks; YC Startup School asks founders to report
  their own numbers. The E-Cell dashboard (#97) should rank on server counts
  only, precisely because that is the one thing no self-report tool can copy.
- **Do not let the ladder grow past five phases.** Every phase added lengthens
  a climb that most builders already fail to finish. TRACTION earns its place
  because it is where revenue starts; nothing else clears that bar, and
  fundraising, scaling and exit talk remain outside the altitude for the same
  reason the corpus refuses them.

## Two duplicate pairs

Independent lenses arrived at the same feature twice. Pick one of each and
close the other before building, rather than shipping both:

- **#65 and #93** — a self-declared launch date. #65 is the simpler field;
  #93 adds the never-overwritten slip trail.
- **#84 and #95** — the week read back. #84 renders it as a dashboard card;
  #95 delivers it as a `SYSTEM` message row and later over Telegram.

## The index

Priority and effort as labelled on each issue.

### Journey and flow
| # | P | E | Title |
|---|---|---|---|
| [60](https://github.com/mahendra2890/masterji/issues/60) | now | L | TRACTION — the terminal phase after the post |
| [61](https://github.com/mahendra2890/masterji/issues/61) | now | S | Light the finish line on launch proof, not arrival |
| [62](https://github.com/mahendra2890/masterji/issues/62) | next | M | Gates that count kinds, not just rows |
| [63](https://github.com/mahendra2890/masterji/issues/63) | next | M | Pivot without amnesia |
| [64](https://github.com/mahendra2890/masterji/issues/64) | next | S | Days-in-phase is a fact the coach can see |
| [65](https://github.com/mahendra2890/masterji/issues/65) | later | S | A launch date, declared not enforced |

### Playbook corpus
| # | P | E | Title |
|---|---|---|---|
| [66](https://github.com/mahendra2890/masterji/issues/66) | now | S | Getting the Conversation (cold outreach) |
| [67](https://github.com/mahendra2890/masterji/issues/67) | now | S | The First Rupee (pricing and the money ask) |
| [68](https://github.com/mahendra2890/masterji/issues/68) | next | S | Picking the One Idea |
| [69](https://github.com/mahendra2890/masterji/issues/69) | next | S | Reading the Nos (pivot or persist) |
| [70](https://github.com/mahendra2890/masterji/issues/70) | next | S | Writing the Post (launch copy in the builder's rooms) |
| [71](https://github.com/mahendra2890/masterji/issues/71) | later | S | First Users by Hand (do things that don't scale) |
| [72](https://github.com/mahendra2890/masterji/issues/72) | later | S | Amendment: the thirty-minute slice |

### Pre-idea coaching
| # | P | E | Title |
|---|---|---|---|
| [73](https://github.com/mahendra2890/masterji/issues/73) | now | S | Price the commit honestly on the commit screen |
| [74](https://github.com/mahendra2890/masterji/issues/74) | now | M | A choosing-an-idea playbook, wired to one place |
| [75](https://github.com/mahendra2890/masterji/issues/75) | now | S | A register for "is this even the right idea?" |
| [76](https://github.com/mahendra2890/masterji/issues/76) | now | M | Sharpen-the-goal: title edit while nothing is banked |
| [77](https://github.com/mahendra2890/masterji/issues/77) | next | L | The Workshop: a turn-metered room before the goal |
| [78](https://github.com/mahendra2890/masterji/issues/78) | next | S | Problem mining from the builder's own week |
| [79](https://github.com/mahendra2890/masterji/issues/79) | next | M | Parking lot capped at three, then forced choice |
| [80](https://github.com/mahendra2890/masterji/issues/80) | later | M | Commit-confidence as arithmetic |

### Robustness and UX
| # | P | E | Title |
|---|---|---|---|
| [81](https://github.com/mahendra2890/masterji/issues/81) | now | S | The night-owl rule |
| [82](https://github.com/mahendra2890/masterji/issues/82) | now | S | Never lose typed work: persist the three drafts |
| [83](https://github.com/mahendra2890/masterji/issues/83) | now | S | Throttles and input caps on the LLM-backed endpoints |
| [84](https://github.com/mahendra2890/masterji/issues/84) | next | M | The week, read back: a deterministic weekly recap |
| [85](https://github.com/mahendra2890/masterji/issues/85) | next | S | Take the record with you: plain-text export |
| [86](https://github.com/mahendra2890/masterji/issues/86) | next | M | Account deletion (with export as the exit ramp) |
| [87](https://github.com/mahendra2890/masterji/issues/87) | next | M | Installable PWA, and web push for the planned nudges |
| [88](https://github.com/mahendra2890/masterji/issues/88) | later | S | The record past 90 rows: stop truncating silently |
| [89](https://github.com/mahendra2890/masterji/issues/89) | later | S | Focus management for the three modals |
| [90](https://github.com/mahendra2890/masterji/issues/90) | later | S | The gap as a fact: "last complete day" in the prompt |

### Competitive and ecosystem
| # | P | E | Title |
|---|---|---|---|
| [91](https://github.com/mahendra2890/masterji/issues/91) | now | M | Count people, not conversations, at the VALIDATION gate |
| [92](https://github.com/mahendra2890/masterji/issues/92) | now | S | The server checks whether the link loads |
| [93](https://github.com/mahendra2890/masterji/issues/93) | next | M | A launch date the server holds |
| [94](https://github.com/mahendra2890/masterji/issues/94) | next | M | The record as a page you can hand to someone |
| [95](https://github.com/mahendra2890/masterji/issues/95) | next | S | Sunday reads the week back — computed, never asked |
| [96](https://github.com/mahendra2890/masterji/issues/96) | later | S | Declare the hour, not just the task |
| [97](https://github.com/mahendra2890/masterji/issues/97) | later | L | E-Cell dashboards rank by the ledger, not the deck |
| [98](https://github.com/mahendra2890/masterji/issues/98) | later | M | LAUNCH holds one number |
