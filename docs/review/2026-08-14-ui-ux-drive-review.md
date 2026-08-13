# UI/UX review — 14 August 2026, from driving the running app

A snapshot, not a maintained document. It reviews `main` at `d5caec9`, and like its two
predecessors it is meant to age. Nothing here is load-bearing for the claims in
[README.md](../../README.md) — if the two ever disagree, the README is the product and
this is an opinion about it.

It follows [13 August (product)](2026-08-13-product-review.md) and
[14 August (tech and flow)](2026-08-14-tech-and-flow-review.md). Both read the tree.
**This one ran it.** Everything below was measured in a browser against a real Django
server, on the viewport sizes this product's stated audience actually holds, and every
number in it is a measurement rather than an estimate.

The 16 proposals live as GitHub issues **#174–#189**. What is written here is the part
that does not survive being cut into sixteen pieces: which three lead, what was checked
and found good, and what was deliberately not recommended.

## How it was produced, and what that is worth

A worktree, its own Django and Next dev servers, and seven seeded accounts standing in
the states where retention is decided: first morning in IDEA, mid-VALIDATION with the
evening owed, the gate met, three nights on one person, a push-back with refused tries
behind it, forty days at LAUNCH, and a broken streak. Each screen was then measured with
`getBoundingClientRect` at **360×640** (a budget Android, which is what "tier-2/3
builder" means in device terms), **390×844**, and **1280×800**.

Four limits worth stating:

- **No LLM key was set**, so nothing here is a judgement about what the coach *says*.
  That turned out to be useful in one direction: it exercised the model-unreachable path
  for free, which is reported below as the best-handled failure in the product.
- **Seeded states are not lived states.** Four things I first wrote down as defects were
  artifacts of seeding through the ORM rather than the API, and were withdrawn after
  checking: a missing welcome message, a "today" row dated yesterday, a phase window
  reading `14 Aug — 14 Aug`, and duplicate `/api/coach/state/` calls (React StrictMode in
  dev — `reactStrictMode` is unset, so Next 16 defaults it on). None are product bugs.
- **Uploads were off** (no R2), so the attach control and the vision path were not seen.
- **Contrast, line length and the palette were checked and found good**, so they are not
  in the findings. Every foreground/background pair in `globals.css` clears 5.4:1 and
  most clear 6.5:1; coach messages measure 69 characters per line at 1280px, inside the
  comfortable band. This paragraph exists so the next reviewer doesn't re-derive it.

## The three findings that lead

**1. On a phone, the one thing the product asks for every day is below the fold.**
At 360×640, on a builder's first morning, `Declare it` sits at y=750 in a 640px viewport
— **110px below the fold**, reachable only by scrolling. At 390×844 it is at y=704, 83%
of the way down. What occupies the space above it is the goal card: **363px**, 43% of the
phone viewport, holding the title, the stepper, days-in-phase, the phase hint, an empty
`0/1` bar, `Request phase advance` and `close this goal` — nothing a builder acts on
today, and one control whose only possible outcome on day one is a refusal.

The evening half does not have this problem, and the reason is instructive: pressing
`File tonight's proof` focuses the proof box, so the browser scrolls it into view. The
morning box gets no such treatment, because on the morning screen there is no press to
hang it on.

The fix is a CSS `order` inside the existing `@media (max-width: 820px)` block so
**Today precedes The goal** on the single-column layout. The goal card is orientation and
the Today card is the errand; the pane is even named "Today". Desktop keeps two columns
and is unaffected. This is the cheapest change in the review and the one most directly
pointed at the daily loop.

**2. The four transitions a builder earns are worth five words; the one they are given
free is worth a hundred and seven.** Creating a goal writes `views.WELCOME` — 107 words
that brief IDEA completely: the problem statement, the route to the people, one place
they already are, why, how to get a conversation, plus the loop rule and the file-it rule.
Advancing a phase writes, verbatim and measured through the API:

```
Phase unlocked: VALIDATION → BUILD.
```

Five words. Meanwhile the counter resets to `0/2 proofs toward LAUNCH`, the full bar
becomes an empty one, `Request phase advance` returns as the card's prominent control,
and the green `Earned.` line disappears on the next render. **The screen after the win
looks worse than the screen before it**, and the phase the builder just unlocked is
explained by one nine-word hint that is the same for every builder forever.

This is not #156. That issue asks the *builder* for a line at phase entry and stores it
on `PhaseTransition`; it is filed `next`/M and it is right. What is missing and unfiled
is the inverse and cheaper half: a `PHASE_BRIEF` dict beside `WELCOME`, one COACH message
per transition, on the moment `AdvanceView` already writes to the transcript. The two
compose — brief the phase, then ask what it will produce — and the brief should land
first, because it is `now`/S and it is the asymmetry that hurts.

**3. The header costs 150px on the device this product is for, and it grows with
success.** At 360px the header wraps to three rows — brand; then the tone switch,
current-and-best streak and lifetime total; then How it works, What's new, sign out. That
is **150px, 23% of a 640px viewport, on every screen, forever**, and the badges that
cause the wrap only exist once a builder has a run going. The more days they bank, the
more chrome they get.

Downstream, on the chat pane at 360×640, the log is left with **184px of client height** —
roughly three or four lines. A coach reply of 40–80 words is 300–500px tall, so the pane
whose entire purpose is a conversation shows a third of one turn at a time. The chrome
around the conversation (header 150, pane nav 45, mode bar and caption ~60, composer 48,
composer note 48) is **two and a half times the conversation**.

The precedent for the fix is already in the tree. `.phaseDays` was deliberately put on
the goal card rather than beside the streak, and its comment says why: *"At 375px that row
is already documented as full."* The same argument retires the streak and lifetime badges
from the header to the goal card, next to the days-in-phase line they are the same kind of
fact as. That recovers a header row on every screen at no cost to any control's position.

## The rest, in the order worth doing

- **A push-back is painted the colour of a crash.** `.pushedBack` and `.error` /
  `.errorBanner` are all `var(--bad)`. The moment of highest drop-off risk in the
  product — your evening's work was refused — is rendered in the same red as *the app
  broke*. `.offPhase`, which is merely advisory, gets the nicer treatment: a left border,
  `--surface-2`, accent. Give the push-back that callout shape and reserve `--bad` for
  faults. This softens the voice and touches no gate.
- **The first thing the coach ever says arrives scrolled past its own opening.** WELCOME
  is 107 words and renders 477px tall inside a 452px log, and the log pins to the bottom
  on mount, so the top **207px is off-screen** — including `Goal locked: "…"`. A new
  builder's first contact with Masterji begins mid-clause. Fix in the pin effect: when
  the newest message is taller than the log, scroll to that message's top rather than the
  log's bottom. That is what a chat should do for any long incoming turn, not just this
  one.
- **The primary actions are below the touch target the repo already decided on.**
  `Declare it` 37px, `Submit proof` 37px, `Commit` 40px, `Request phase advance` 34px,
  goal input 40px, example chips 32px, stepper chips ~25px, and **`reword` is 16px tall by
  40px wide**. `sign out` is 44px, and its comment argues the case: *"the cost of a miss
  here is a session."* The cost of a miss on `Declare it` is the day's declaration.
- **The commit box clips the example that teaches its own size.** On the first screen
  after signup, the placeholder `e.g. Tiffin-delivery app for my college` needs 247px and
  the input gives it 217px, because the input and `Commit` share a row at 243px + 89px.
  Stack them below ~420px.
- **`Request phase advance` is the loudest control on the card when it can only refuse.**
  At `0/1` on day one it is the goal card's only button. The comment defends pressability
  below the bar — *"being told exactly what is missing is the coaching"* — and that is
  right; what is wrong is the emphasis. Make it a quiet link while `have === 0` and
  promote it to a button once there is something to count.
- **The phase drill-in cannot be found on a phone.** `.stepDone` announces itself with
  `cursor: pointer`, a `:hover` background and a `title` — three affordances that do not
  exist on touch. The chips are ~25px tall and the three non-tappable ones look identical
  to the two tappable ones. A genuinely good feature ("the days spent in this phase") is
  effectively desktop-only.
- **The commit screen's paragraph is 223px of prose before the box** — 90 words, 26% of a
  390×844 viewport, at the moment of least investment. It is doing five jobs at once (one
  thing at a time; test not finish; two minutes a day; the first ask is desk work; closing
  is free and an idea that dies reads as tested). It is also quoted whole inside the tour's
  step 1, so a visitor who takes the tour reads it twice. Two sentences and a disclosure
  for the rest.
- **The earn is quieter than the refusal.** A refusal gets ninety words; `Earned. BUILD is
  yours to open.` gets six, and the bar stays marigold at 100% so nothing but the text
  changes colour. Turn the fill green at the bar, and carry one line of what was banked
  into the next phase rather than resetting to a bare `0/2`.
- **What's new nags an account that has no history with the product.** The dot is lit
  whenever `masterji.changelog.seen` is unset, so it is on for every brand-new browser —
  an invitation to leave the first task and read the changelog of a product they met a
  minute ago. Stamp `seen` with the newest entry on first ever mount, so the dot only
  ever means *something shipped since you last looked*.
- **The mode caption restates the switch.** `Coach me` / `Think with me` is a two-option
  control with the live one lit, and directly under it a caption names the lit mode again
  ("Assignments and push-back"). It costs ~28px of a 184px log at 360px. Drop it below
  ~420px; the tour is where the modes are explained, per the existing decision.
- **Two cycles on one day are indistinguishable in the record.** Rows carry a date and the
  declaration, so a builder who legitimately runs a second cycle — explicitly supported,
  *"real work counts when it happens"* — gets two rows reading `13 Aug` with no way to
  order them. An ordinal or a time on the second and later rows of a date.
- **The phase modal's header can contradict its body.** The date range comes from
  `phaseWindow(transitions)` while the rows come from the stamped `checkin.phase`, and
  `Masterji.tsx` already argues correctly that dates must not be trusted for the rows.
  Then it trusts them for the heading. Derive the displayed range from the rows shown, or
  prefer them when the two disagree.
- **The flattering exit is the filled button.** In the retire box, `I achieved it` is
  primary and first, `I'm dropping it` is secondary, at any phase — including 2/3 in
  VALIDATION, where the first is almost certainly false. Both exits must stay (they do,
  and `reads_as` computes the honest label from proofs regardless), but below the finish
  line neither deserves the emphasis.

## What is already right, and should be left alone

Reported so the next review doesn't spend its budget here.

- **The model-unreachable path is the best-handled failure in the product.** The typed
  message stays in the log, the notice is drawn as a dashed non-bubble with no avatar so
  it is never attributable to the coach, and `Send it again` is right there. Verified
  live, with no API key set.
- **Draft persistence, and the evening's focus jump.** Text and link come back into the
  box; the attachment note says out loud what could not be restored; `File tonight's
  proof` focuses the box it reveals and the browser scrolls it into view.
- **The gate's honesty under load.** `3 proofs banked, 1 person` and `The count is there.
  Still needed: …` both say what is on the record before what is missing, which is the
  hardest copy in the product to get right and it is right.
- **The record's week-long cut** with `Show all 40` behind it, and the fetch deferred to
  the press.
- **Modal focus and Escape**, the `aria-pressed` pane switcher, and `.who` hidden on
  mobile.
- **Tour steps 2–4**, which lead with a headline and one paragraph and then annotate real
  mocks with numbered callouts. Step 1 is the only weak one, and its weakness is the
  commit paragraph it quotes.

## Reprioritised or endorsed, not refiled

- **[#144](https://github.com/mahendra2890/masterji/issues/144) — raised `next` → `now`,
  and it should be first.** The question asked of this review was where builders drop off.
  Fifteen of the sixteen findings above are ranked on argument, because nothing counts
  whether the loop works. This review can prove that `Declare it` is 110px below the fold;
  it cannot say whether that costs a declaration. #174 is about day 1 and #175 is about
  days 8–20, one of them is worth doing first, and no evidence in this repository can say
  which. Every number #144 wants is a `COUNT` over rows the server already holds. The
  label was moved and the argument recorded on the issue.
- **[#87](https://github.com/mahendra2890/masterji/issues/87) (PWA + push) stays `next`
  but is the only retention *channel* in the backlog.** Everything in this review makes
  the app better once opened; nothing in it gets a builder to open the app on day 4.
- **[#143](https://github.com/mahendra2890/masterji/issues/143)** already covers the door
  not mentioning the Workshop, and already carries the counter-argument that the landing
  page is long. The commit-screen paragraph above is a different screen and is not filed.
- **[#117](https://github.com/mahendra2890/masterji/issues/117)** gains an argument: four
  of the findings here are pure-CSS layout facts at a named viewport, which is the one
  frontend category that is cheap to pin and expensive to regress silently.

## What was deliberately not recommended

- **No bottom tab bar or app-shell chrome.** The pane switcher already does this job in
  45px and it is sticky. A bottom bar would buy nothing and cost the composer.
- **No onboarding tour, coach marks, or empty-state illustrations inside the app.** The
  tour exists, is reachable from the header, and is deliberately a bridge rather than a
  manual. Finding 2 asks the coach to speak at a transition, in the transcript, which is
  where this product already explains itself.
- **No celebration animation on the gate.** The earn should be louder in *words and
  colour*, not in confetti; the product's voice is a referee's.
- **No moving `close this goal` off the goal card.** The commit screen promises closing is
  free, so it must stay reachable and quiet, which it is. Only the advance button's
  emphasis is wrong.
- **No second column on mobile, and no collapsing the goal card behind a disclosure.**
  Reordering answers finding 1 completely; hiding the phase state would cost the
  orientation the card exists to give.

## The index

The 16 proposals live as GitHub issues **#174–#189**, each carrying the mechanism, the
measurement behind it, and the files it lands in. Every one is `effort:S` — not by design,
but because this review found no large UI problems. The product's screens are well built;
what is wrong with them is cheap.

### Robustness and UX
| # | P | E | Title |
|---|---|---|---|
| [174](https://github.com/mahendra2890/masterji/issues/174) | now | S | The daily action is below the fold on a phone — order Today before The goal |
| [176](https://github.com/mahendra2890/masterji/issues/176) | now | S | The header costs 150px at 360px, and it grows with the streak |
| [177](https://github.com/mahendra2890/masterji/issues/177) | now | S | A push-back is painted the colour of a crash |
| [178](https://github.com/mahendra2890/masterji/issues/178) | now | S | The coach's first message arrives scrolled past its own opening |
| [179](https://github.com/mahendra2890/masterji/issues/179) | now | S | The daily controls are under the 44px this repo already decided on |
| [180](https://github.com/mahendra2890/masterji/issues/180) | now | S | The commit box clips the placeholder that teaches its own size |
| [181](https://github.com/mahendra2890/masterji/issues/181) | now | S | "Request phase advance" is the loudest control when it can only refuse |
| [182](https://github.com/mahendra2890/masterji/issues/182) | next | S | The phase drill-in has no affordance on a touchscreen |
| [185](https://github.com/mahendra2890/masterji/issues/185) | next | S | The What's-new dot nags an account with no history to catch up on |
| [186](https://github.com/mahendra2890/masterji/issues/186) | next | S | The mode caption restates the lit switch, at 28px of a 184px log |
| [187](https://github.com/mahendra2890/masterji/issues/187) | next | S | Two cycles on one day are indistinguishable in the record |
| [188](https://github.com/mahendra2890/masterji/issues/188) | later | S | The phase modal's heading can contradict its own rows |

### Journey and flow
| # | P | E | Title |
|---|---|---|---|
| [175](https://github.com/mahendra2890/masterji/issues/175) | now | S | An earned phase gets five words; signing up gets a hundred and seven |
| [184](https://github.com/mahendra2890/masterji/issues/184) | next | S | The bar never turns green, and the win resets to a bare 0/2 |
| [189](https://github.com/mahendra2890/masterji/issues/189) | later | S | The flattering exit is the filled button below the finish line |

### Pre-idea coaching
| # | P | E | Title |
|---|---|---|---|
| [183](https://github.com/mahendra2890/masterji/issues/183) | next | S | The commit screen spends 223px on prose before the box |

A note the issues cannot carry: **#174, #176, #179 and #186 are one afternoon's work in
four tickets.** All four are measurements at 360×640 and all four land in the same
`@media (max-width: 820px)` block. Built in one pass they share a single re-measure of the
phone layout; built separately, each pays for that measurement again.

And a second: **#175 and #184 are the two halves of one moment** — the transcript and the
card, at the instant a phase unlocks. Either alone leaves the other still saying that the
reward for three real conversations is an empty bar.
