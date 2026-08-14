# Frontend architecture review — 15 August 2026

A snapshot, not a maintained document. It reviews `main` at `975a6bb`, and like its
four predecessors it is meant to age. Nothing here is load-bearing for the claims in
[README.md](../../README.md) — if the two ever disagree, the README is the product and
this is an opinion about it.

It follows [13 August (product)](2026-08-13-product-review.md), [14 August (tech and
flow)](2026-08-14-tech-and-flow-review.md), [14 August (UI/UX,
driven)](2026-08-14-ui-ux-drive-review.md), [14 August
(security)](2026-08-14-security-review.md) and the coaching-prose review. Those five
between them read the tree, drove the running app, drove the model, and read the coach's
words.

**None of them read the frontend as code.** The UI/UX review measured the screens this
file draws; this one is about the file. It is the first review of `app/Masterji.tsx` as
an artifact to be changed rather than a product to be used, and it exists because that
file is now a third of the frontend and the place where every parallel session collides.

The four proposals live as GitHub issues **#282–#285**.

## How it was produced, and what that is worth

`app/Masterji.tsx` read end to end — all 3,622 lines, not sampled — plus `lib/`, the
component directory, `masterji.module.css`, and the two server caps that decide how much
data the file holds at once. Every number below was measured on this tree at `975a6bb`
rather than estimated, and the two that could have been asserted instead of measured
(the cost of the per-render arithmetic, and whether the CSS has gone stale) both came
back *against* the finding I expected, and are reported that way.

Baseline on this tree: `npm run build` succeeds, `npm run test:web` is **78 tests across
14 files, all passing**.

Three limits worth stating:

- **Nothing was driven.** This is a reading review; the 14 August UI/UX review is the
  one that ran the app, and where the two touch, its measurements are the ones to trust.
- **The render-breadth finding is structural, not a stopwatch reading.** I measured the
  derived arithmetic and it is cheap (below), but I did not instrument React itself, so
  there is no "N renders per keystroke" number here — only the structural claim that
  there is no boundary to stop one.
- **`app/demo/Tour.tsx` (949 lines) and `lib/coach-api.ts` (1,498 lines) were read for
  coupling only**, not reviewed on their own terms. Both are plausibly worth their own
  pass; `coach-api.ts` especially, as the second-largest file in the frontend.

## The two findings that lead

### 1. Eighty-seven percent of the component cannot call a hook

`Masterji()` runs from line 577 to line 3622 — 3,045 lines. It calls **68 hooks: 44
`useState`, 10 `useRef`, 9 `useEffect`, 5 `useCallback`, and zero `useMemo`.** Every one
of them is between line 578 and line **971**.

Then come two early returns — `if (!state) return <DashboardShell />` at
[line 1304](../../app/Masterji.tsx#L1304), and the whole no-goal screen returning at
[line 1501](../../app/Masterji.tsx#L1501). After the first of them, the Rules of Hooks
make a hook call illegal for the rest of the function.

So **lines 972–3622 — 2,650 lines, 87% of the component — are a hook-free zone.** The
dashboard, the goal card, the Today card, the record, the chat pane, the phase drill-in
and the day panel are all inside it.

This is not inferred. The file says it, at
[line 1888](../../app/Masterji.tsx#L1888), in a comment explaining why a value computed
over every row of the record is recomputed on every render:

> Not memoised: hooks are illegal this far down the component (the no-goal branch above
> returns first) …

Three things follow, and they are the actual cost:

- **There is nowhere to put a memo boundary.** The zero `useMemo` in a 3,622-line
  component is not an oversight; it is the only legal value.
- **New state is declared ~2,000 lines from where it is used.** `viewDay` is declared at
  line 665 and read at line 3613. `filingNow` at 689, read at 2844. A reviewer checking
  one card has to hold the top of the file in their head.
- **`void justRetired;`** at [line 1892](../../app/Masterji.tsx#L1892) — a statement
  whose only job is to stop the linter complaining about a variable consumed in a branch
  that already returned. That line is the structure leaving a mark.

**This lands on work that is already queued.** #276 (`suggest_declaration`) adds a
drafted-declaration offer to the Today card, and #274 adds a reword box to it. Both
write state that belongs to a card at line ~2800 and both will have to declare it at
line ~730, next to the workshop's drafts and the onboarding screen's pivot flag. That is
the fifth and sixth pieces of state to make that trip.

Filed as **#282**.

### 2. The file has no tests, and cannot have any

`npm run test:web` is 78 passing tests over 14 files. **Every one of those files tests a
pure module** — 13 in `lib/`, one in `app/waking/`. **Not one test imports a React
component**, and neither `@testing-library/react` nor a DOM environment (`jsdom`,
`happy-dom`) is in `package.json`. Component testing here is not thin; it is not
installed.

That would be a defensible trade — except that the untested file is where the product's
decidable rules live. A partial inventory of logic currently expressible only as JSX:

| In `Masterji.tsx` | What it decides |
| --- | --- |
| `eveningOpen` (line 1934) | Six clauses deciding whether tonight's form is on screen |
| `dayOpen` (1904) | Whether the day is unfinished — drives the phone's pane dot |
| `draftWaiting` / `notesRunning` (1916, 1924) | Which of three sentences the composer note shows |
| `gateKey` (192) | Whether a gate refusal has been overtaken by the record |
| `isUnsettled` (357) | Whether the evening is over |
| `saidBefore` (328) | Which words a retry button will re-send |
| `missingPieces` (460) | The pieces tonight's draft still owes |
| record slice (3153–3166) | Which rows the card shows, and whether to draw the cycle column |

`isUnsettled` is the sharpest of these. Its own comment says it

> Mirrors views.UNSETTLED, which decides the same thing for the server — if these two
> ever disagree, the card and the endpoint disagree about whether the evening is over.

That is a named cross-seam invariant, with nothing on either side pinning it.

**The repo already knows how to fix this, and has a rule for it.** `lib/record.ts` opens
by citing the decision: *"Pure and separate for the reason #117 settled: this is
decidable arithmetic over data the payload already holds."* `lib/gate.ts` exists because
`isEarned` got two readers and the two could have drifted. `lib/log-pin.ts` is the
strongest precedent of all — it extracts **DOM arithmetic** as a pure function over a
plain `{scrollTop, scrollHeight, clientHeight, newestTop, newestHeight}` object, and
`lib/log-pin.test.ts` pins it with numbers measured off a real 390×844 account. No DOM
library, no component harness, no new dependency.

So the recommendation is not "adopt a testing stack". It is **finish applying #117** to
the eight rules above, in the shape the repo already uses.

Filed as **#283**.

## The rest, in short

**3. `renderRoom` is 175 lines of JSX in a closure (#284).**
[Line 1324](../../app/Masterji.tsx#L1324) defines the workshop — meter, transcript,
openers, composer, closed-door copy — as a function inside the component, called from
the onboarding screen (1823) and from behind the goal card (2648). The comment defends
the choice correctly against the wrong alternative:

> A function rather than a component so it keeps the refs it is given: a nested component
> would be a new type on every render, remounting the composer and taking the caret out
> of it mid-sentence.

That is true of a component *nested in the render body*. It is not true of a
module-level component taking those refs as props, which is the actual fix. As written,
this is the single largest obstacle to splitting the file: it is the one block that both
screens depend on, so neither screen can move without it.

**4. State outlives the screen it belongs to (part of #282).**
The component never unmounts across a goal's whole lifecycle — retiring takes the render
down the no-goal branch in place. The file has had to defend against this twice by hand:
`gateKey` (line 192) puts the goal id in its key so a refusal from a dead goal cannot
greet a new one, and `allDays` (line 682) stamps its rows with a `goalId` for the same
reason. Both comments explain the hazard well. Both are the same hazard, and #276's
declaration offer will be the third thing to need the same guard.

**5. Render breadth — and the measurement that argues against overstating it.**
There is no memo boundary anywhere, so a keystroke in the chat composer re-renders the
goal card, the stepper, the gate meter, the metric series, the record and every message
bubble. At the server's caps that is 90 check-ins (`CHECKIN_HISTORY`) and 30 messages
(`HISTORY_LIMIT`), and more once `Show all` fetches the uncapped record (#141).

I expected the per-render arithmetic to be the story and **it is not.** Measured on this
tree, warm, 5,000 iterations:

| rows | `cycleOrdinals` | `newestFirst` |
| --- | --- | --- |
| 7 (the card's default) | 0.9µs | 0.2µs |
| 90 (the payload cap) | 8.4µs | 5.8µs |
| 400 (a year, `Show all`) | 43.2µs | 47.1µs |

Fourteen microseconds at the cap. That is not a defect and should not be filed as one —
which is the point of measuring it. The honest finding is the structural one: **there is
no place to put a boundary if this ever does start to hurt**, and that is finding 1, not
a separate problem. Recorded here so the next reviewer doesn't file it as a performance
bug on inspection alone.

**6. Two dead CSS classes (#285).** `masterji.module.css` defines 217 classes.
`.archiveRow` (line 2251) and `.historyPhase` (line 1387) are referenced nowhere in the
repository — their definitions are their only occurrences.

## What was checked and found good

Written down so the next reviewer does not re-derive it.

- **The CSS has not rotted.** 215 of 217 classes are live. For a 3,066-line stylesheet
  that grew alongside a 3,622-line component, that is a better result than the file sizes
  suggest, and it is the reason finding 6 is two lines rather than a cleanup project.
- **`lib/` is exemplary and is the model for everything above.** Fifteen modules, thirteen
  tested, each opening with a comment saying which failure it exists to prevent. The
  frontend does not need a new convention; it needs the existing one carried across the
  component boundary.
- **The comment density is an asset, not bloat.** Roughly half this file is prose, and it
  is the good kind: nearly every constant and branch records the failure that produced it
  (`EVENING_FROM`, `enterSends`, `isSendKey`, `usePersistedDraft`, the `{" "}` note at
  line 1430 that is load-bearing against a real SWC bug). **Any extraction must carry the
  comments with the code it moves.** A refactor that "tidies" them would destroy more
  value than the refactor creates, and this paragraph exists to make that non-negotiable.
- **`Tour.tsx` borrows rather than copies.** It imports `masterji.module.css` and wears 62
  of the app's own classes, under a stated rule: *"Borrowed pixels, not redrawn ones — a
  guide drifts from its product the moment it keeps a second copy of the styling."* The
  card markup itself is still duplicated, which is what the three-mirrors problem is; the
  styling is not, and that half was done right.
- **The two composer paths were unified correctly.** `isSendKey` (line 171) exists because
  the workshop's copy of the send predicate was missing the `enterSends()` half and fired
  half-written turns on phones. It takes fields rather than a React event *specifically*
  so a third box cannot diverge by copying four fifths of it. That is the same instinct
  this review is asking to apply eight more times.

## What was deliberately not recommended

- **A state library.** Redux, Zustand, or a query cache would all be a bigger change than
  the problem justifies. The one-payload-plus-refetch model is coherent, documented at the
  top of the file, and the `refresh()`-returns-state detail at line 738 shows it has
  already been thought about. Nothing here is a data-flow problem; it is a scope problem.
- **`@testing-library/react` and a DOM environment, as step one.** Every rule listed in
  finding 2 is expressible as a pure function over plain data, which is how `log-pin`
  already tests DOM arithmetic at zero dependency cost. If component tests are wanted
  later that is a separate argument, and it should be made on its own.
- **Splitting the file by screen and stopping there.** Three files — onboarding,
  dashboard, modals — would leave each one still holding a hook-free tail, because the
  early returns are what create the zone, not the line count. The split has to put each
  screen in its own component so each screen owns its own hooks; anything less moves the
  problem without fixing it.
- **Touching this before #274/#276 land.** Flagged when this review was commissioned and
  it still holds: those two rewrite the Today card region, and #282's split would conflict
  with them everywhere. The order is in the next section.

## The order worth building in

1. **#285** (two dead classes) — trivial, independent of everything, mergeable today.
2. **#283** (extract and pin the predicates) — touches `lib/` and replaces expressions in
   `Masterji.tsx` with calls. It is the *lowest-conflict* of the three real items, because
   it changes few lines in the big file, and it is worth doing **before** the split: it
   means the split is moving code that already has tests under it.
3. **#274 + #276** — the queued journey work, unblocked and unaffected by 1 and 2.
4. **#284** (`renderRoom` → a component) — after #276, because it is the prerequisite for
   the split and the smaller half of it.
5. **#282** (lift the early returns) — last, and only once the card region is settled.

## The index

| # | P | E | Title |
|---|---|---|---|
| [282](https://github.com/mahendra2890/masterji/issues/282) | next | L | 87% of `Masterji.tsx` cannot call a hook — the two early returns, and the state that outlives its screen |
| [283](https://github.com/mahendra2890/masterji/issues/283) | now | M | Eight decidable rules live only as JSX, in the one frontend file with no tests |
| [284](https://github.com/mahendra2890/masterji/issues/284) | next | M | `renderRoom` is 175 lines of JSX in a closure, and the reason given defends the wrong alternative |
| [285](https://github.com/mahendra2890/masterji/issues/285) | later | S | Two CSS classes are defined and referenced nowhere |
