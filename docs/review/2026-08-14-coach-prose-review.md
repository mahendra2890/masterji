# Coaching prose and corpus review — 14 August 2026

A snapshot, not a maintained document. It reviews `main` at `074d97f`, and like its
predecessors it is meant to age. Nothing here is load-bearing for the claims in
[README.md](../../README.md) — if the two ever disagree, the README is the product and
this is an opinion about it.

It follows [13 August (product)](2026-08-13-product-review.md),
[14 August (tech and flow)](2026-08-14-tech-and-flow-review.md),
[14 August (UI/UX, from driving the app)](2026-08-14-ui-ux-drive-review.md) and
[14 August (security)](2026-08-14-security-review.md). Everything below is new
relative to all four backlogs. The security review merged while this one was being
written and touched nothing it cites, which is why the commit above is one behind
`main`.

The first three recorded the same limit, in almost the same words: *"No LLM key was
set, so nothing here is a judgement about what the coach says."* Nobody has reviewed
the coaching content. That is this review's subject.

The 8 proposals live as GitHub issues **#258–#265**. What is written here is the part
that does not survive being cut into eight pieces.

## How it was produced, and what that is worth

The whole corpus read end to end — sixteen playbooks, 9,863 words — plus `prompts.py`
(2,463 lines), `guidance.py`, the gate refusals in `gates.py`, and every
builder-facing string in `views.py` and `nudges.py`. Then a worktree with its own
Django and Next servers, and two seeded accounts driven through the API: one English,
one whose `tone` was set to `HINGLISH` **before** its goal existed, so that every
sentence the server wrote for it was written under the Hinglish setting.

Every number below is measured. The measurements were taken with a script over the
live modules rather than by counting by hand, and the ones that matter are repeated in
the issues so they can be re-run.

### The limits, and they are the point

- **There is no model API key on this machine**, verified. `OPENAI_API_KEY` and its
  neighbours are unset. So this review covers the **deterministic half** of what a
  builder reads — which turns out to be 2,123 words of server-written prose in
  Masterji's voice, plus the 9,863-word corpus that shapes the other half — and says
  nothing about a single sentence the model produced.
- **The seam was not scripted, on purpose.** It would have been easy to stub `llm.py`
  and write about the output as though it were the model's. A scripted delta tests
  plumbing, not prose. What a key would settle is listed at the end of this document,
  as a list, so the work can resume the moment one exists.
- **One proof was accepted through the ORM.** Reaching VALIDATION needs an `ACCEPTED`
  row and the only road to one is the judge. So the check-in was declared and filed
  through the API — real date, real phase, real declaration, real transcript — and
  only `proof_status` and `proof_parts` were set by hand. Everything else in this
  review was seeded through `POST /api/coach/goals/` and the check-in endpoints.
- **Uploads and push were off** (no R2, no VAPID keys), so the nudge copy was read
  rather than received on a phone. The finding about it is about which strings exist,
  which needs no device.

## The three findings that lead

### 1. The tone switch moves the model's half of Masterji's voice and none of the server's

`EN | हिं` sets `User.tone`, which selects `prompts.HINGLISH_RULE` into three system
prompts. That is the whole of its reach. **Every `Message.Role.COACH` row the server
writes itself is English, on every account, and the builder cannot tell the
difference** — those rows render in the same bubbles, under the same avatar, as the
Hinglish ones.

Driven live on a Hinglish account, in order: `views.WELCOME` (101 words, his first
words ever, written by `GoalsView`); the gate's refusal at `0/1` with
`guidance.GATE_NUDGE[IDEA]` behind it; `views.PHASE_BRIEF[VALIDATION]` on the earned
transition. Three consecutive coach bubbles, all English. The only Hinglish anywhere
on the screen was `prompts.STOCK_UNJUDGED["HINGLISH"]` — the line that fires when the
model could not be reached — sitting on the Today card in green.

That is the product speaking Hinglish exactly once, to report its own outage.

Four more are worse than the others because of where they land.
`views.OFFER_NO_DECLARATION`, `OFFER_DAY_CLOSED`, `OFFER_LANDED` and `NOTES_LANDED`
are not separate rows: `views.py:2769` and `:2812` append them to the streamed turn
and save them as its content. So on a Hinglish account an English sentence is
concatenated onto the end of a Hinglish reply, inside one bubble.

The measurement: **2,123 words of server-written builder-facing prose. 104 of them —
three stock check-in reactions — have a Hinglish twin.** The Monday digest
(`weekly.py:219`) is the one fully bilingual surface, and it is a `SYSTEM` pill rather
than the coach.

The mechanism is not missing, which is what makes this filable rather than a wish.
`weekly.py:239` wrote a Hinglish person-counter (`1 aadmi` / `{n} log`) specifically
because handing an English noun to a Hinglish sentence was wrong; `gates.try_advance`
calls `guidance.people()` for the same count in the sentence that refuses a builder,
in English, forever. `prompts.py:1188` states the rule outright — *"a builder who
asked to be spoken to in Hinglish should not be answered in English precisely when
something has gone wrong"* — and applies it to three strings out of thirty.

Why this is not a nice-to-have. The README's competitive claim is that Overlord and
Pre are neither *"priced nor voiced for India"*, and #192 already moved the switch
onto the pre-goal screen on the argument that Hinglish *"is not a preference among
preferences."* The switch is reachable now. What it reaches is half the voice.

**#258** is the transcript half — the three surfaces that render as Masterji speaking.
**#259** is the nudge, which `prompts.py:2436` already names as a gap in its own
comment.

### 2. The corpus outgrew the claim that justifies its architecture

The README's answer to "why no vector DB" is that the corpus is small enough to read:
*"The corpus is deliberately small enough to read in ten minutes"* (`README.md:229`).
The curation policy opens with *"ten small markdown files"*
(`playbooks/README.md:3`). The tour tells a visitor, before they have signed up, that
the playbooks *"are about ten minutes of reading"* (`app/demo/Tour.tsx:757`).

Measured across the three review points:

| reviewed at | files | words | at 200 wpm |
|---|---|---|---|
| `6d0f4ed` — 13 Aug product review | 6 | 2,787 | ~13 min |
| `a2446fc` — 14 Aug tech review | 10 | 5,248 | ~26 min |
| `074d97f` — today | **16** | **9,863** | **~49 min** |

The claim was written when it was roughly true and has not moved since. Six surfaces
carry it: `playbooks/README.md:3` and `:9`, `README.md:229`, `prompts.py:5`,
`Tour.tsx:757`, and `CorpusCurationTests`'s own docstring at `tests.py:4086`, which
restates the promise and then checks three other things.

There is an honest version of the claim and it is better than the current one, because
no builder ever reads sixteen files. They read their phase's:

| phase | files | words | at 200 wpm |
|---|---|---|---|
| IDEA | 3 | 2,206 | ~11 min |
| VALIDATION | 4 | 2,535 | ~13 min |
| BUILD | 4 | 2,332 | ~12 min |
| LAUNCH | 3 | 1,520 | ~8 min |
| TRACTION | 2 | 1,281 | ~6 min |

*Ten minutes* is true per phase and false for the folder. Say both (**#260**).

**Underneath it is the finding that matters.** The curation policy has four numbered
steps for how a method earns its way in and **no budget, no cap and no eviction
rule** — nothing anywhere in the repo bounds the corpus. Every review so far has
proposed playbooks and every one has landed: six files were added between the tech
review and today, the corpus grew 60% in file count and 88% in words in two days, and
the review that wrote *"Ten playbooks, readable in ten minutes"* into its own
**not-recommended** list is the review that proposed four of the six and put the other
two on its build order.

That is content-library creep — the failure the 13 August thesis-guardian list names —
arriving not through one bad file but through ten good ones. None of the six should be
reverted; every one filled a gate that was refusing people on a condition nothing
taught. What is missing is the sentence that makes the next one a trade instead of an
addition (**#261**).

For scale: the assembled system prompt with every optional block absent is 30,015
characters in IDEA and 31,748 in VALIDATION, and the playbooks are **29–44%** of it.
`#152` shipped token accounting as OpenTelemetry span attributes, which are a no-op
without an OTLP endpoint, so those are the first numbers anyone has for this.

### 3. The corpus is monolingual about work that will not happen in English

Sixteen playbooks, 9,863 words, written for a builder the README places in a tier-2
college in India. **Two lines mention language**, both in `writing-the-post.md:55-56`,
and both are about the register of a launch post.

The conversations are the problem. VALIDATION's bar asks for *"3 things they said in
their own words"* (`guidance.PROOF_HINT`, `bar.py`'s `quotes` part). A builder
interviewing a mess contractor, a kirana shop owner or a Block C hosteller is not
having that conversation in English, and nothing in the corpus tells them what to do
about it. `customer-conversations.md:27` says *"Note exact phrases. Their words become
your landing page"* and stops. `getting-the-conversation.md:19-31` hands them a
four-line first message, scripted in English down to the clause *"I'm a second-year
at ___"*, for a stranger they will actually message in Hindi.

This is not a request for translated playbooks, and it is not a content-library
addition. It is one paragraph of method in the two files where the question lands: the
words go down in the language they were said in, a translated quote is a paraphrase
and a paraphrase is the thing the bar is trying to prevent, and the first message is
written in the room's language rather than the one the template is in.

It composes with finding 1. The product is voiced for India in the model's replies,
and in neither the corpus that teaches the method nor the sentences the server writes
in his name (**#262**).

## The rest, in the order worth doing

- **The source-credit rule is enforced by a hand-kept list that exempts the two files
  breaking it** (#263). `playbooks/README.md:22` — *"They credit the source by name…
  Borrowed authority is fine; hidden authority is not"* — is the load-bearing rule
  under README.md's whole "who's holding the gate" argument, and `Tour.tsx:757` tells
  a visitor the playbooks *"credit their sources by name."* Fourteen do.
  `over-engineering.md` and `launch-checklist.md` do not. `CorpusCurationTests`
  enforces the rule against `NEW_PLAYBOOKS`, a dict maintained by hand
  (`tests.py:4096`), and those two are original-era files that structurally cannot be
  in it. Reading the directory instead is a two-line change and it forces a decision
  that is Mahendra's, not a session's: credit a source, or say in the file that this
  one is original and why the policy allows that.
- **"Three rungs is the count" against a ladder the corpus defines as four** (#264).
  `guidance.py:169` says it in the refusal a builder reads at the moment quitting
  looks reasonable; `launch-checklist.md:9-20` numbers four rungs. `PROOFS_REQUIRED`
  counts three *proofs*, one carrying `action` — which is rung 4. So the sentence
  tells a builder to climb three of a four-rung ladder and that one of the three must
  be the fourth. `PHASE_BRIEF[LAUNCH]` gets it right (*"three nights"*, four rungs
  named), which is the wording to copy.
- **`problem-statement.md` demands four things; three surfaces of the bar ask for
  three** (#265). The playbook's anatomy is who / **the trigger** / what they do today
  / why the workaround fails, and it says *"If you can't fill in all four honestly,
  you have an idea, not a problem statement"* (`:24`, repeated at `:62`). The trigger
  appears in neither `bar.BAR[IDEA]`'s `problem` part (`bar.py:71-76`) nor
  `GATE_NUDGE[IDEA]` nor `PROOF_HINT[IDEA]`. The drift is in the safe direction — the
  corpus asks for more than the gate, and `BAR_RULE` forbids raising the bar past what
  is written — but it means a builder who reads the playbook properly is told they
  have failed a test the server never set. Bring the file to the bar; do not move the
  bar.

## What is already right, and should be left alone

Reported so the next review does not spend its budget here.

- **The corpus is genuinely method, not content.** Every file names a source, gives a
  move that fits in one evening, and ends with the same *"Signals you're hiding"*
  shape so a builder learns the form once. The examples are the target builder's
  actual life rather than translated Valley material: kirana shops writing credit in a
  notebook, ₹210 for ₹90 of food when the mess shuts at 21:30, Instagram resellers
  matching UPI texts against DMs, PYQ-sharing and event-discovery named as campus
  tarpits, *"the idea that sounds best when you describe it to a placement panel."*
  Judged as coaching rather than as prose, this holds.
- **The corpus and the bar agree about what a proof must contain, everywhere.** Each
  playbook's *"What counts as PROOF for Masterji"* section was read against
  `guidance.PROOF_HINT` and `bar.BAR` for all five phases. VALIDATION's are
  word-for-word the same list. The two disagreements found are about counts, not
  contents, and are #264 and #265. Given this repository's history with a rule stated
  in four places, that is the check worth not re-running.
- **The corpus cross-references instead of overlapping.** Four files open by saying
  what they do *not* cover and naming the neighbour that does
  (`getting-the-conversation`, `people-you-know`, `reading-the-nos`, `first-touch`).
  Nothing in 9,863 words is a second file's argument restated.
- **`reading-the-nos.md:52-59` is accurate about the record.** It tells a builder that
  INVALIDATED *"needs at least two accepted proofs from VALIDATION onward"*, which is
  exactly `gates.INVALIDATED_AT = 2` over `contact_proofs`. A playbook quoting a
  server constant correctly is rare enough to say out loud.
- **`prompts.py` is the best-documented file in the repository and its rules are
  conditioned, not shouted.** Every register block — `WHEN_IT_IS_NOT_ABOUT_THE_WORK`,
  `WHEN_THEY_DOUBT_THE_IDEA`, `CLOSING_IS_THEIRS`, `THE_CALENDAR` — carries the
  evening that caused it and a condition that stops it firing unprompted, and each one
  ends by saying it moves the turn and not the gate. `ANSWER_WHAT_THEY_ASKED` exists
  because a softer refusal became a cheaper one; that is a second-order failure
  somebody actually noticed.
- **`guidance.BEATS` is the right shape.** VALIDATION's three rungs — the door, the
  who, the ask — are drawn from that phase's own four playbooks and change what is
  *asked for* while `PROOF_HINT` (what the judge grades against) stays fixed. The
  comment at `guidance.py:44-50` makes the argument better than an issue would.
- **The deferrals are redirects, not scoldings**, and each names the builder raising
  it first. `PHASE_RULES`' *"a fair question asked in the wrong week is not a character
  flaw, and repeating the refusal is how you lose them"* is the right instinct in the
  right place.

## What was deliberately not recommended

The most losable content in any review, because an issue tracker has no way to record
a decision *not* to build something.

- **Do not translate `guidance.PROOF_HINT` or `PROOF_EXAMPLES` into Hinglish**, and
  this is the deliberate scope line on #258. `prompts.judge_bar_for` hands
  `PROOF_HINT` verbatim to the one model call `gates.py` counts. Two language versions
  of that string are two bars, drifting from the moment the second is written — which
  is the exact failure `guidance.py`'s own docstring exists to prevent. #258 covers
  what the coach *says*; the bar he judges against stays in one language and one
  place.
- **Do not translate the playbooks.** Sixteen English files becoming thirty-two files
  in two languages is the content-library creep of finding 2 with a doubling attached,
  and the corpus is the thing #261 is trying to bound. The method is taught in the
  prompt and spoken in the builder's language by the model; that division is correct.
- **Do not add a playbook for any of the findings above.** #262 is filed as an
  amendment to two existing files for the reason the 14 August review filed #161 as
  one: the corpus cannot afford a seventeenth file while nothing bounds the sixteenth,
  and the language question belongs inside the two files that already teach the
  conversation rather than beside them.
- **Do not put the mode explanation back in the mode bar.** `Masterji.tsx:3406-3417`
  records that a *"What's the difference?"* disclosure was built there and removed on
  Mahendra's call — three text elements in a control strip is clutter, and the tour is
  where the modes are explained. The caption (*"Assignments and push-back."* /
  *"Questions and options, not assignments."*) is one clause about the lit mode and is
  the right amount. Restated here because it is the obvious thing to re-propose after
  reading `THINKING_MODE` and noticing how much it changes that the builder is never
  told.
- **Do not relabel the tone switch.** `हिं` is Devanagari and `HINGLISH_RULE` asks for
  Roman script, which looks like a mismatch and is not one: the button names the
  language, not the script, and `HI` in Latin would be worse for the reader it is for.
  Considered and kept.
- **Do not soften the gate refusals while translating them.** #258 is a language
  change and nothing else. `gates.try_advance`'s wording — what is banked first, what
  is owed second — was called out as *"the hardest copy in the product to get right
  and it is right"* by the 14 August UI review, and the Hinglish version has to be a
  translation of that sentence rather than an occasion to rewrite it.
- **Do not give the workshop or the reopened room their own corpus.** Both load
  `choosing-an-idea.md` and nothing else, and that is correct: they are rooms for
  choosing, not phases, and a room with its own reading list is a phase wearing a
  different name.

## What a model key would settle, and nothing else can

Listed so this is a pause rather than a conclusion. Every one of these is a question
about prose the model produces, and every one is unanswerable here.

1. **Does the register survive Hinglish?** `HINGLISH_RULE` is 34 words riding on top
   of `RESPECT_RULE`, `BAR_RULE`, three registers and four playbooks. Whether *"hard on
   the work, easy on the person"* holds in Hinglish, or collapses into either
   stiffness or the mockery `RESPECT_RULE` forbids, is a reading of real output.
2. **What actually changes between `Coach me` and `Think with me`?** `THINKING_MODE`
   is 148 words in a 5,900-word prompt. Whether the reply a builder gets is
   recognisably a different mode, or the same coaching with a question mark on it, is
   the only test that matters and it needs both replies to the same message.
3. **Do the beats read as coaching or as a score?** `BEAT_BLOCK` forbids reading the
   count out loud. Whether rung 2's press — *"the second is the one that decides
   whether this is a problem or a friendship"* — lands as instruction or as the app
   keeping a tally is a question about tone in output.
4. **Is a push-back specific enough to act on tonight?** `SUBSTANCE_RULE` demands it.
   Nothing deterministic can check it.
5. **Does the stalemate diagnosis actually split the two cases?** `STALEMATE_RULE`
   asks the model to decide whether the work is missing or the two of them are failing
   to understand each other. That decision is the product's most consequential piece
   of prose and it has never been read.
6. **Does the evidence fence hold?** `EVIDENCE_NOT_INSTRUCTIONS` says an instruction
   inside the fence is worth nothing rather than worth a refusal. Both halves — not
   obeyed, and not punished — need adversarial submissions against a live judge.
7. **Does 44% of the prompt being playbooks change the reply?** Finding 2 measures the
   corpus's share. Whether a fifth file in VALIDATION dilutes instruction-following is
   the empirical half of #261, and it is the half that would turn a budget from a
   judgement into a number.

## The index

Priority and effort as labelled on each issue.

### Voice and register
| # | P | E | Title |
|---|---|---|---|
| [258](https://github.com/mahendra2890/masterji/issues/258) | now | M | Every coach row the server writes is English, on a Hinglish account |
| [259](https://github.com/mahendra2890/masterji/issues/259) | next | S | The evening nudge is English-only, and `prompts.py` already says so |

### Playbook corpus
| # | P | E | Title |
|---|---|---|---|
| [260](https://github.com/mahendra2890/masterji/issues/260) | now | S | Six surfaces say "ten minutes"; the corpus is sixteen files and forty-nine |
| [261](https://github.com/mahendra2890/masterji/issues/261) | now | S | The curation policy has an admission rule and no budget |
| [262](https://github.com/mahendra2890/masterji/issues/262) | now | S | The corpus is monolingual about work that will not happen in English |
| [263](https://github.com/mahendra2890/masterji/issues/263) | now | S | The source-credit rule is checked against a hand-kept list that exempts the two files breaking it |
| [264](https://github.com/mahendra2890/masterji/issues/264) | next | S | "Three rungs is the count" against a ladder the corpus defines as four |
| [265](https://github.com/mahendra2890/masterji/issues/265) | next | S | `problem-statement.md` demands four things; the bar asks for three |

A note the issues cannot carry: **#258, #260 and #262 are the same finding seen three
times.** The product's claim is that it is voiced for India. #258 says the server does
not speak the language, #262 says the method never mentions it, and #260 says the one
document that would bound the corpus teaching it has been wrong about its own size
since the day the corpus started growing. Built together they are one decision about
what "voiced for India" means; built apart, each is a copy fix.

And a second: **#260, #261 and #263 all land in
[`playbooks/README.md`](../../backend/coach/playbooks/README.md) and its test.** That
file is the corpus's spec, it is out of date in three separate ways, and one pass over
it costs one re-read of the folder instead of three.
