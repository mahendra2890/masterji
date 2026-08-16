"""Builder-facing phase copy — the words the product says on its own.

Distinct from prompts.py, which is what Masterji says *through the LLM*. This
module is the deterministic half: the stepper hint, what tonight's proof must
contain, worked examples of proofs that were accepted, and the concrete action
attached to a gate refusal. None of it depends on a model being reachable, and
all of it is the single source of truth — the dashboard reads these over the
API rather than keeping its own copy, because two copies drift and only one of
them is the one gates.py enforces.

It is also every OTHER sentence the product says in its own voice — the welcome
written at goal creation, the brief for a phase just earned, the receipts, the
refusals and the workshop's spent-turn exits, at the bottom of this file. They
were in views.py until #293, which meant a reviewer asked to check what the
coach says had to know that half of it was in a file called views. There is one
home now, and this is it: coach-visible copy goes here, not next to the code
that happens to send it.

Examples are written here, not harvested. The repo is public and the corpus a
builder learns from should be as auditable as the gate that judges them.
"""

from typing import NamedTuple

from .models import Phase

# One line under the goal title. What this phase is for, in the imperative.
#
# The phase's constant — true at every count, and what a builder reads once the
# phase's own bar has been met. Below the bar a phase may have BEATS, and then
# this line is replaced by the rung's; read it through phase_hint(), never
# straight out of the dict, or a builder gets the phase in general on an evening
# the product knows something more specific about.
PHASE_HINT = {
    Phase.IDEA: "Write the problem statement, and where you'd find these people — no outreach yet.",
    Phase.VALIDATION: "Talk to real customers. Bring notes, not opinions.",
    Phase.BUILD: "Smallest thing a real user can touch this week.",
    Phase.LAUNCH: "In front of strangers. Ask for commitment.",
    Phase.TRACTION: "Make one stranger come back, or pay. Repeat beats reach.",
}

# What tonight's proof has to contain. Mirrors each phase playbook's
# "What counts as PROOF for Masterji" section — kept in one place so the
# check-in form cannot promise something the playbook doesn't teach.
#
# The same bar is also in bar.BAR, broken into parts the server can count. This
# one is prose because it is what a builder READS; that one is data because it
# is what suggest_proof is shaped from and what decides how many entries a list
# is short. They are two faces of one bar and they have to be changed together
# — bar.py's docstring says the same thing from the other side.
#
# Deliberately the one string in this module that BEATS does not touch, and the
# reason is the whole of why beats are safe. prompts.judge_bar_for hands this to
# the single model call gates.py counts, so a version of it that escalated with
# the count would refuse at 3/3 what it accepted at 1/3 — the goalposts moving
# between two evenings of one phase, which is the failure prompts.py:758-783
# exists to have removed. A beat changes what is ASKED FOR; the bar is what
# COUNTS, and it is the same at every rung.
PROOF_HINT = {
    Phase.IDEA: (
        "What to submit: your one-paragraph problem statement, plus the route "
        "to these people — one specific place they already are, what makes "
        "you think they're there, and how you'd get one conversation this "
        "week. No names needed. You are not messaging anyone yet; "
        "conversations are VALIDATION's work."
    ),
    Phase.VALIDATION: (
        "What to submit: notes from ONE real conversation — who you spoke to, "
        "3 things they said in their own words, what they last did about this "
        "problem, and what commitment you asked for (and whether you got it)."
    ),
    Phase.BUILD: (
        "What to submit: a link to something running, or clear evidence a real "
        "user touched it — screenshot, log line, their message."
    ),
    Phase.LAUNCH: (
        "What to submit: a link to your public post, evidence of a stranger's "
        "action or payment, or a real rejection with the reason they gave."
    ),
    Phase.TRACTION: (
        "What to submit: evidence someone came back without being asked — what "
        "they did the second time and when — or a payment: who, how much, for "
        "what."
    ),
}

# Worked examples. A builder stuck at the gate rarely needs the rule restated —
# they need to see the shape of an accepted answer. Deliberately mundane and
# specific: a plausible college-scale proof, not a highlight reel.
#
# IDEA carries two on purpose, and the second one is the point. One example
# gets read as the bar, and the hostel example alone sets it at "users you can
# already count" — the builder standing in the queue with them. The reseller
# example is the same bar met by a builder with no audience, whose users never
# announce themselves anywhere countable. That case is most of them, and it is
# the case the route replaced a name-list to serve.
PROOF_EXAMPLES = {
    Phase.IDEA: [
        "Second-year hostellers miss dinner when labs run past 21:00 — mess "
        "shuts at 21:30. They order delivery at roughly 2x menu price, or skip "
        "the meal. Where they are: the Block C mess queue at 21:15, and the "
        "block WhatsApp group (180 members). Why I think so: I've been in that "
        "queue all semester. First conversation: Thursday, ask the two people "
        "behind me in the queue what they ate last night.",
        "Instagram resellers doing 10–30 orders a week lose track of who paid "
        "— they scroll DMs at night matching orders against UPI texts by hand. "
        "Where they are: the sellers' Telegram group I joined last week, 340 "
        "members. Why I think so: 14 messages there last month were people "
        "asking how others keep track of payments. First conversation: reply "
        "to the next person who asks and offer to hear how they do it today.",
    ],
    Phase.VALIDATION: [
        "Priya, 2nd yr, Block C. Last Tuesday she got back at 22:10, mess was "
        "shut, paid ₹210 for about ₹90 of food. Her words: \"I just don't eat "
        'some nights." Asked to watch her do it Thursday — she said yes.',
        "Ramesh, mess contractor. Says 40–50 plates go to waste most nights. "
        "Already tried a WhatsApp group for counts; it died in a week because "
        "nobody replied by 18:00. Wouldn't share numbers. Gave me an intro to "
        "the Block B contractor.",
    ],
    Phase.BUILD: [
        "Link: tiffin-count.vercel.app — the form saves to a sheet. Priya "
        "submitted the first real order at 21:15 tonight, unprompted.",
        "Screenshot of Ramesh's WhatsApp: he sent tomorrow's plate count "
        "through the form instead of calling me. First time he used it "
        "without being asked.",
    ],
    Phase.LAUNCH: [
        "Posted in the college WhatsApp group (340 members). 11 sign-ups in "
        "two hours, 3 paid the ₹50 deposit.",
        "Rejection: Block D contractor said no. He settles cash daily and "
        "won't wait for a weekly payout — that's the objection to solve next.",
    ],
    Phase.TRACTION: [
        "Priya ordered through the form again on Thursday — second time this "
        "week, and I never reminded her. Screenshot of both rows in the sheet.",
        "Block B contractor paid ₹99 for the month by UPI after two weeks of "
        'using it free. Payment screenshot and his "continue karo" message.',
    ],
}

# Appended to a refusal from gates.try_advance. The refusal already says what
# is missing; this says what to go and do about it tonight. It has to work
# standing alone: the dashboard's advance button hits the gate with no LLM in
# the loop, so this is the only coaching a builder gets at the exact moment
# quitting looks reasonable.
#
# The phase's constant, like PHASE_HINT above and read the same way — through
# gate_nudge(), because a phase with BEATS has a better sentence for the rung the
# builder is actually standing on.
GATE_NUDGE = {
    Phase.IDEA: (
        "One paragraph: who has this problem, what they do about it today, "
        "and why that's bad. Then the route — one specific place these people "
        "already are, why you think so, and the first conversation you'd get "
        "this week. No names, no outreach until VALIDATION. Desk work; one "
        "evening. Can't name the place? That's the 'who' still being a guess "
        "— make it specific enough to have an address."
    ),
    Phase.VALIDATION: (
        "One conversation. Ten minutes, someone who already has the problem. "
        "Ask what they did the last time it happened — not whether they'd use "
        "your app. Notes tonight."
    ),
    Phase.BUILD: (
        "Put the smallest working piece in front of one person who already "
        "talked to you. A link that loads is a night's proof — but one of the "
        "two has to be somebody actually using it, so send it to one of your "
        "VALIDATION people tonight and write down what they did with it."
    ),
    # LAUNCH had none of these while it was the last phase — there was nothing
    # to refuse, so nothing to say. It has an exit now, and the ladder in
    # launch-checklist.md is already written one rung per evening.
    Phase.LAUNCH: (
        "One rung tonight: send it personally to one person from your "
        "VALIDATION notes, or post it in one room where these people already "
        "sit — with the ask attached. The three this gate counts are accepted "
        "proofs, not rungs: the ladder has four rungs and you climb one a "
        "night. One of the three nights has to be a stranger actually doing "
        "something, so make the ask concrete enough that doing it leaves a "
        "trace you can screenshot."
    ),
}


class Beat(NamedTuple):
    """One rung inside a phase: what to ask for with N of the bar already banked.

    A phase bar is a count, and a count is a constant — so the product said the
    same three sentences to a builder on their third conversation as to one who
    had never spoken to anybody. The work is not the same work. The first
    conversation is a door problem; the second is a WHO problem; the third is an
    ask problem, and the playbooks teach all three separately (see below).

    What a beat is not: a second gate. It replaces PHASE_HINT and GATE_NUDGE for
    one rung and adds `press` to the coach's prompt, and that is the whole of its
    reach. It never touches PROOF_HINT, bar.BAR, PROOFS_REQUIRED or the judge's
    prompt — nothing a beat says can make an evening's proof count for more or
    less than it counted before. The comment on PROOF_HINT says why that line is
    the one that must not move.
    """

    # Replaces PHASE_HINT[phase] at this rung. Same contract as that string: one
    # line under the goal title, imperative, and it has to read as what the phase
    # is for rather than as a progress report.
    hint: str
    # Replaces GATE_NUDGE[phase] at this rung. Same contract again: it is
    # appended to a refusal that arrives with no LLM in the loop, so it has to
    # name tonight's action while standing entirely alone.
    nudge: str
    # What the coach is told to press for, for prompts.beat_block. Never a bar
    # and never a score to read out — see prompts.BEAT_BLOCK, which carries the
    # guard rather than repeating it here.
    press: str


# One tuple per phase, indexed by what the phase has already banked, and only
# where nothing else in the product already varies the ask.
#
# VALIDATION is the whole table today, and that is a decision rather than a
# starting point. Every other multi-proof phase already escalates inside itself
# through Need.kinds: BUILD's second evening is told "still needed: evidence a
# real user touched it" by gates.kinds_owed, and LAUNCH's by the same route, so
# their asks already move as the count does. VALIDATION's Need(n=3, people=True)
# carries no kinds at all — the count IS the whole of its bar — which is exactly
# why it was the phase with nothing to say. Beats fill that hole and are not a
# second opinion next to one that already exists.
#
# So a phase earns a tuple here when its bar is a bare count, not when its bar is
# above one. Adding one is a tuple and nothing else: every reader below falls
# through to the phase's constant, which is what all five phases get today.
#
# The tuple covers the rungs BELOW the bar — one beat per proof the phase costs,
# checked in the tests against PROOFS_REQUIRED — and at or above it a builder
# gets the phase's constant back, because a count that is met has no next rung
# and "third conversation" is a false sentence to a builder who has had three.
#
# The copy is not new advice. All three rungs are in VALIDATION's own four
# playbooks and always have been; what did not exist was anything that reached
# for the right one on the right evening. Sources, rung by rung:
#   1  getting-the-conversation.md — ask for advice never pitch, a named day, and
#      "silence is arithmetic: send five to get one", which is the sentence that
#      keeps a builder from reading one unanswered message as a dead problem.
#   2  people-you-know.md — "after two conversations with people you know, spend
#      the next on somebody who has no reason to be nice to you", the intro as
#      the real prize, and three flatmates as one data point in three shirts.
#   3  customer-conversations.md's third rule, dig for commitment not
#      compliments, plus reading-the-nos.md on sorting the pile by what it cost
#      the other person.
BEATS: dict[Phase, tuple[Beat, ...]] = {
    Phase.VALIDATION: (
        # 0 banked — the door. Nothing else in the phase happens until this does,
        # and the failure here is not a bad conversation, it is no conversation:
        # one message sent, no reply, and a builder concluding the problem isn't
        # real. So the arithmetic is in the nudge, where the refusal will carry it
        # at the exact moment that conclusion looks reasonable.
        Beat(
            hint="One conversation is the whole of tonight. Ask about last "
            "time, not next time.",
            nudge="One conversation. Ten minutes, someone who already has the "
            "problem. Ask what they did the last time it happened — not "
            "whether they'd use your app. Nobody replied yet? That is the "
            "rate, not the verdict: send five tonight to get one back, and put "
            "a day in the message so it's a decision they can make now. Notes "
            "tonight.",
            press="Nothing is banked in this phase yet, so tonight's whole job "
            "is getting into one room — the first yes is the hard one, and "
            "nothing else in this phase happens until it lands. Press for the "
            "ask itself rather "
            "than the plan around it: who they will message or go and stand in "
            "front of, and which day they will name in it. If they have sent "
            "messages and heard nothing, say the arithmetic out loud — five "
            "sent to get one back — because a builder who sent one, heard "
            "nothing and concluded the problem isn't real has tested nothing "
            "at all. A clumsy first conversation with a flatmate beats a "
            "fourth evening rewriting the message.",
        ),
        # 1 banked — the WHO. gates.accepted_proofs already counts distinct
        # people here, and until now the only thing that ever said so was the
        # refusal: a builder learned the rule by having a second night with the
        # same person not count. Said here it is the instruction for the evening
        # instead, which is the same fact arriving early enough to act on.
        Beat(
            hint="Someone new, and not someone like the first. Ask who has it worse.",
            nudge="Someone new. This phase counts people rather than evenings, "
            "so another night with the same person is honest work that buys no "
            "ground here — and that is worth knowing now rather than from a "
            "refusal later. Make it somebody with no reason to be kind to you. "
            "The shortest route there is the first person's own answer to "
            '"who do you know who has this worse than you?" — an intro opens '
            "a door a cold message won't. Same ten minutes, same questions.",
            press="One person is banked, and the second is the one that "
            "decides whether this is a problem or a friendship. Press on WHO, "
            "not on technique. This phase counts distinct people, so a second "
            "night with the same person is real work that buys no ground here, "
            "and three people from one corridor is one data point wearing "
            "three shirts — say that now, while it is still an instruction. "
            "Heard first from the gate, it arrives as two nights of work being "
            "taken away. The move to put in front of them is the "
            "introduction: ask the first person who they know who has this "
            "worse than they do. An intro is both the route to a stranger and "
            "a commitment in its own right.",
        ),
        # 2 banked — the ask. bar.BAR[VALIDATION] has carried a `commitment`
        # part since the day it was written and nothing in the product ever
        # escalated to it, so the one line in a builder's notes the other person
        # had to pay for was the one nothing ever asked for by name.
        Beat(
            hint="Third conversation. Ask for something that costs them — an "
            "hour, an intro, money.",
            nudge="The third one, and it turns on the ask. End it with "
            "something that costs them — an hour, an introduction, a look at "
            "their books, money — and write down what you asked for and "
            'whether you got it. "Sounds great, keep me posted" is a '
            "rejection wearing a smile. Then read all three notes together: if "
            "nobody gave anything up, that is this week's finding, and it "
            "means the ask was too big, too vague, or aimed at the wrong "
            "person.",
            press="Two people are banked, and the third is where this phase "
            "either produces something to act on or does not. The part of the "
            "bar that has been in it all along and rarely arrives is the "
            "commitment — what they asked this person to give up, and whether "
            "they got it. Press for that ask before the conversation rather "
            "than after: an hour, an introduction, a look at their books, a "
            'deposit. Praise for the idea is not a commitment, and "keep me '
            'posted" is a no wearing a smile. When the third is in, have them '
            "read all three notes together — three people naming the same "
            "workaround is a segment they can build for, and an empty "
            "commitment column after three conversations is the week's finding "
            "rather than a dead idea: it means the ask was too big, too vague, "
            "or aimed at the wrong person.",
        ),
    ),
}


def beat(phase: Phase, banked: int) -> Beat | None:
    """The rung this builder is standing on, or None for the phase's constant.

    `banked` is gates.accepted_proofs(goal) — the phase's OWN count, which on
    VALIDATION is distinct people and not rows. That distinction is the whole
    reason this reads a number computed there instead of counting anything
    itself: two accepted nights about one hostelmate are one person, and a beat
    keyed on rows would send that builder to "ask for the commitment" while the
    gate is still waiting for a second person to exist.

    None above the bar as well as off it, so `banked` past the last rung falls
    back to the phase's constant rather than clamping to the final beat.
    """
    beats = BEATS.get(phase)
    if not beats or banked < 0 or banked >= len(beats):
        return None
    return beats[banked]


def phase_hint(phase: Phase, banked: int) -> str:
    """The line under the goal title, for the rung they are actually on."""
    rung = beat(phase, banked)
    return rung.hint if rung else PHASE_HINT[phase]


def gate_nudge(phase: Phase, banked: int) -> str | None:
    """What to go and do about a refusal tonight, for the rung they are on.

    None-able exactly as GATE_NUDGE.get() was, because a phase without one is a
    real case (TRACTION) and gates.try_advance already handles it.
    """
    rung = beat(phase, banked)
    return rung.nudge if rung else GATE_NUDGE.get(phase)


# Three things to say to Masterji, for a chat log that has nothing in it yet.
#
# The empty log is a cold start with a cost: a builder who never talks to him
# writes every evening's proof from a blank box, because the draft he hands
# back under Today is assembled from the conversation. So the chat is not a
# side room — it is how the evening gets cheap — and "Talk it through…" over an
# empty pane is a poor invitation to the one habit that makes the rest work.
#
# Written in the builder's voice, not his: these are questions somebody would
# actually type, phase-shaped, and two of the three in each set are the doubt
# that stalls people in that phase rather than a request for instructions.
# Tapping one fills the box and leaves the sending — and the editing — with the
# builder, the same bargain GOAL_EXAMPLES and the proof draft already make.
#
# They are suggestions, not a menu the coach is limited to, and none of them
# touches the gate: gates.py has never read a message.
OPENERS = {
    Phase.IDEA: [
        "Who exactly has this problem?",
        "Where would I find these people?",
        "Is this goal too big?",
    ],
    Phase.VALIDATION: [
        "What do I ask so they don't just say yes?",
        "Where do I find one person to talk to this week?",
        "They said they'd use it — does that count?",
    ],
    Phase.BUILD: [
        "What's the smallest thing I can put in front of someone?",
        "How rough is too rough?",
        "I'm stuck on what to build first.",
    ],
    Phase.LAUNCH: [
        "Where do I put this in front of strangers?",
        "What do I ask a stranger for?",
        "Nobody replied. Now what?",
    ],
    Phase.TRACTION: [
        "Nobody came back — how do I find out why?",
        "How do I ask for money without losing the only user I have?",
        "One person keeps using it. What now?",
    ],
}


def people(n: int) -> str:
    """A person count as the builder reads it.

    Here rather than at either call site because two of them say it — the gate's
    refusal and the coach's state block — about the same number in the same
    breath, and a count phrased two ways is how one product starts sounding like
    two. The dashboard says it a third time in TSX and cannot import this; that
    copy is the one to check when this wording changes.
    """
    return "1 person" if n == 1 else f"{n} people"


def for_phase(phase: Phase, banked: int) -> dict:
    """The whole builder-facing bundle for one phase, for the API payload.

    Same four keys it has always had, and only one of them moved. `banked` is
    required rather than defaulted because a default here is a wrong answer that
    looks like a right one: 0 is a real rung, so a caller who forgot to pass the
    count would serve a builder on their third conversation the sentence written
    for somebody who has never spoken to anybody.

    What the client sees, decided rather than fallen into:

    `phase_hint` is the beat. It is one line, it is rendered under the goal title
    every day, and it is the only string in this bundle whose job is "what is
    tonight for" rather than "what does this phase accept" — so it is the one the
    escalation belongs in.

    `proof_hint` is NOT, and its own comment says why: it is the bar, the judge
    reads it, and a bar that moves with the count is the goalposts moving.

    `proof_examples` is not either, and for the neighbouring reason. VALIDATION's
    two are a conversation where the commitment was got and one where it was
    refused and an intro came instead. Showing only the second at rung three
    would narrow the bar to what that rung is pressing for, which is the failure
    PROOF_EXAMPLES' own comment records about IDEA: one example gets read as the
    bar.

    `openers` is not either, and this one is a judgement rather than a rule.
    VALIDATION's three are already the three freezes of this phase — how do I
    stop them saying yes, where do I find one person, does a "they'd use it"
    count — and they line up with the rungs closely enough that a per-rung set
    would be four more strings buying no new information.
    """
    return {
        "phase_hint": phase_hint(phase, banked),
        "proof_hint": PROOF_HINT[phase],
        "proof_examples": PROOF_EXAMPLES[phase],
        "openers": OPENERS[phase],
    }


# The workshop has no phase, so it gets its own set (models.Workshop). Same
# bargain as OPENERS above: tapping one fills the composer and leaves the
# sending with the builder.
#
# These four are the actual freezes, not four flavours of "help me brainstorm":
# no idea at all, too many ideas, the fear that the idea is too obvious to be
# worth doing, and the belief that somebody else has already settled it. The
# first one is also the condition the coach's week-walk is keyed to — a builder
# who taps it has told the room they arrived empty-handed, which is the one case
# where walking their week is the right opening move.
#
# The fourth is not a restatement of the third, which is why it is here rather
# than folded into it: "too obvious" is a fear about whether the idea is WORTH
# doing, "someone's already built this" is a belief that the question is already
# ANSWERED and the work is therefore pointless. Different freeze, different
# answer — and the answer is this product's own thesis, so the room should not
# have to improvise it. The register that answers it is a block in
# prompts.WORKSHOP_SYSTEM, keyed to this opener the way the week-walk is keyed
# to the first.
WORKSHOP_OPENERS = [
    "I don't have an idea yet.",
    "I have three ideas and can't pick.",
    "Is my idea too obvious?",
    "Someone's already built this.",
]


# --- The coach's own sentences, moved here from views.py ------------------
#
# Everything below is what the product says in its own voice at a moment the
# HTTP layer happens to be the one that reaches it: the welcome written at goal
# creation, the brief for a phase just earned, the receipts for a wordless
# tool-call turn, the two refusals and the workshop's spent-turn exits. They
# lived in views.py for no reason but where the code that sends them sits, which
# meant a reviewer asked to check what the coach says had to know that half of
# it was in a file called views.
#
# Moved verbatim, comments included. Nothing here changed wording.

# Named, never pointed at. "Above" was true in no layout the product has:
# on a laptop the check-in is the LEFT column, and on a phone it is behind a
# tab you can't see while you're reading this. Both spellings sent half the
# builders looking in the wrong place on the one screen where they have no
# idea yet which half of the app does what. "Today" is the label on the card
# and on the phone tab, so it survives the breakpoint.
WHERE_TO_FILE = "Today"

# Ends on the gate, not on "talking to me records nothing on its own", which
# is the first thing a builder ever reads from him and told them their half
# of the deal was worthless before they had said a word. It was also out of
# date: he drafts the evening's proof from the conversation, so the chat is
# where the proof comes FROM even though it is not where it lands. Same order
# as the note under the reply box — what he does with it first, the gate
# second — and the promise waits on a declaration for the same reason
# _offer_target does: with no task to hang notes on, there is nothing to write
# up yet.
#
# The second sentence is the commit screen's reframe arriving a moment later,
# and it is here rather than only there because this is the first thing the
# coach himself says: "this is yours now" is the whole of what the builder had
# to go on, and it reads as a lock rather than as the start of a test. The
# reframe is one sentence and no more — the message's job past that point is the
# phase in front of them, and the record promise (an idea that dies in front of
# real people reads as tested) belongs on the screen where the hesitation
# actually happens, not stacked on top of the week's instructions.
WELCOME = (
    'Goal locked: "{title}". Rule one: one goal at a time, and this is yours '
    "now. What you picked is the problem you test first, not an idea you are "
    "stuck with. You start in IDEA — write a one-paragraph problem statement, then "
    "the route to these people: one place they already are, why you think "
    "they're there, and how you'd get one conversation this week. No names "
    "needed, and you won't message anyone until VALIDATION. Declare today's "
    f"task under {WHERE_TO_FILE} and I'll write tonight's proof out of what "
    "you tell me here — but nothing counts until you file it there."
)

# What the phase a builder just EARNED is for, in the register WELCOME uses.
#
# The asymmetry this exists to close: signing up writes the 107 words above,
# which brief IDEA completely, and earning a phase wrote five — gates.py's
# "Phase unlocked: X → Y." — for the four transitions that are the bigger
# context switch of the two. IDEA is desk work the builder was just briefed on;
# BUILD arrives with a different count, a kind requirement the earlier phases
# never had, and a nine-word PHASE_HINT that is the same for every builder
# forever.
#
# Keyed by the phase moved INTO, so IDEA has no entry and cannot: nobody
# advances into it, and WELCOME already briefs it at the only moment a goal is
# ever there.
#
# Distilled from each phase's playbooks rather than written fresh. The corpus
# already says what each phase is for, and a brief teaching something it does
# not would be a second bar arriving by the back door — one the builder reads
# once, at speed, and never sees again. What each one adds past the playbook is
# the COUNT: it is the half PHASE_HINT has no room for, and without it the
# first thing to name the new bar is a refusal.
UNLOCKED_BRIEF = {
    Phase.VALIDATION: (
        "VALIDATION is three conversations with three different people — the "
        "same willing friend three times is one person, and it is the server "
        "counting, not me. Ask what they did the last time this happened, not "
        "whether they would use your app: people are honest about what they "
        "did and fantasists about what they'll do. Each night is one "
        "conversation — who, three things in their own words, what they last "
        "did about it, and what you asked them to give up."
    ),
    Phase.BUILD: (
        "BUILD wants two nights of evidence, and at least one has to be a real "
        "person touching the thing — two links nobody opened is an artifact, "
        "not this phase. Scope by subtraction: whatever the first ten users "
        "could live without goes on the later list, and the later list is "
        "where features go to be forgotten. If it can't be in front of "
        "somebody within a week, it isn't the small version yet."
    ),
    Phase.LAUNCH: (
        "LAUNCH is three nights in front of strangers, and one of them has to "
        "be somebody acting — posting is not somebody acting. Climb one rung a "
        "day: the people who already talked to you, the rooms they sit in, the "
        "public ponds, then the ask. A no with the reason they gave is "
        "evidence and counts; silence is not."
    ),
    Phase.TRACTION: (
        "TRACTION is the last rung — there is no phase above it, and what it "
        "asks for is one stranger who came back on their own, or who paid. Two "
        "people using it once each is not that. Recruit one at a time, "
        "over-serve the first ten embarrassingly, and watch returns rather "
        "than signups: signups are the number that flatters."
    ),
}

# Said when the builder sharpens the wording of a goal nothing has been banked
# against yet. In the transcript rather than only in the response, because the
# transcript is the memory: a title that changed with nothing said about it makes
# every message above it read as though it had always been about the new wording.
#
# Both wordings are named. WELCOME froze the original at the top of the log
# already, so nothing is being hidden — this is the line that connects the two
# without the builder having to scroll for it.
TITLE_SHARPENED = (
    'Reworded: "{before}" → "{after}". Nothing is banked against this goal yet, '
    "so nothing moved — same goal, sharper sentence. The days and the streak are "
    "where they were."
)

# And the refusal, once the record does point at the wording. Names the condition
# rather than the rule, and leaves the honest door open: the sentence about a goal
# kept out of guilt is the one the coach already uses in the personal register.
TITLE_LOCKED = (
    "There is proof on the record filed against this wording, so it stays as it "
    "is — those evenings were for this goal, and renaming it now would quietly "
    "rewrite what they were for. Keep it, or close it honestly and start the one "
    "you'd choose now."
)

# A draft Masterji wrote out of the conversation with no check-in to pin it
# to. It used to end at a server log: the builder had done the work, said it
# out loud, and watched the reply go by with no sign that any of it had been
# written up or thrown away. The draft is theirs, so it goes back to them —
# in the transcript, where declaring first costs them the declaration and not
# the writing-up as well.
#
# Said ONLY when nothing was declared today. There is a second evening with
# nothing to pin a draft to and it is the opposite situation — see
# OFFER_DAY_CLOSED.
OFFER_NO_DECLARATION = (
    "That reads like tonight's proof — but there's no task declared this "
    "morning, so I have nothing to pin it to. Declare one under "
    f"{WHERE_TO_FILE} and file this:\n\n{{offer}}"
)

# The same handed-back draft on an evening that is already finished: today's
# task was declared, proved and closed, so there is no open cycle — and the
# line above would be a flat contradiction of the card the builder is looking
# at, which reads "Declared: <task>" with a green "✓ accepted" under it. It
# said that in real use: a builder closed out a VALIDATION conversation, kept
# talking, described more work, and was told nothing had been declared this
# morning.
#
# So this one names what actually happened and offers the way on. More than
# one cycle a day is a supported thing, not a loophole (see CheckIn's
# docstring) — "Declare another task" is the button waiting on that card.
OFFER_DAY_CLOSED = (
    "That reads like another proof — but today's cycle is already declared, "
    "filed and closed, so I have nothing open to pin it to. If this is a "
    "second piece of real work, declare another task under "
    f"{WHERE_TO_FILE} and file this against it:\n\n{{offer}}"
)

# Said when Masterji spends a whole turn writing tonight's proof and adding
# nothing to it. The draft itself is deliberately NOT repeated here: it is on
# the check-in, where one tap files it, and two copies of one offer means one
# of them does nothing. This is the receipt for the other copy. Without it the
# turn was silent — the work landed on the Today card and the chat, the screen
# the builder was actually watching, showed their message with no answer under
# it. A tool call is not a reason to say nothing to someone who just spoke.
OFFER_LANDED = (
    "Wrote tonight's proof up from what you just told me — it's under "
    f"{WHERE_TO_FILE}, yours to edit before you file it."
)

# The same receipt for a turn that banked a PART of tonight's proof and said
# nothing around it. It has to carry the gap: notes that don't say what is still
# owed read as a finished proof the builder can go and file, and they'd be
# pushed back for a piece nobody told them was missing.
NOTES_LANDED = (
    "Noted what you've given me so far — it's under "
    f"{WHERE_TO_FILE}. Still need: {{missing}}"
)

# The morning's version of OFFER_LANDED: the receipt for a turn that wrote
# today's task down and said nothing around it. Same argument as its neighbour
# — a tool call is not a reason to say nothing to someone who just spoke — and
# the draft is deliberately not repeated here, because it is in the box on the
# card where one tap declares it, and a second copy in the chat is the one the
# builder cannot press.
#
# It has to say that nothing is declared yet. That is the whole difference
# between this and OFFER_LANDED: filing a proof is the end of the day and a
# builder who misreads the receipt has still done the work, but a builder who
# reads this as "declared" spends the day owing a proof against a task the
# server has never been told about.
DECLARATION_LANDED = (
    "Put today's task in the box under "
    f"{WHERE_TO_FILE} — in your words, as I heard them. Nothing is declared "
    "until you press it."
)

# The unlock's version of the two above, and the same argument: a tool call is
# not a reason to say nothing to someone who just spoke (#270 / #310).
#
# It has to say that nothing is named yet, for DECLARATION_LANDED's reason one
# step softer — nothing at all waits on this line, so a builder who misreads the
# receipt loses only the line itself. What it must not do is nag: this is a
# receipt for something they said, not a second ask, and the sentence ends by
# handing the choice back rather than by chasing the press.
PHASE_INTENT_LANDED = (
    "Put that in the box under the phase — your words, as I heard them. It's "
    "not saved until you press it, and it's fine to leave it."
)

# The launch date's version, and the one that has to be most careful about what
# it claims. The others' receipts sit beside things nothing depends on; this one
# sits beside an APPEND-ONLY record whose whole point is that a date, once
# named, is on the trail. A builder who reads this as "committed" believes they
# have a launch day when the server has never heard of one — so the sentence
# says nothing is committed, and names the button that would do it.
LAUNCH_DATE_LANDED = (
    "That day and that room are in the launch box on your card — press Set and "
    "they're on the record. Nothing's committed until you do."
)

# And the goal's wording, the last of them. This receipt has a job the others
# don't: it must not read like the goal has been renamed. The title is on every
# screen the builder looks at, so a receipt they misread is one they check
# against the card two seconds later — which is fine — but the sentence should
# be the one that was true when they read it either way.
#
# It also names the window rather than the button alone. The control is gone the
# moment a proof banks, and a builder who is told to press something that will
# not be there tomorrow has been told half of it.
GOAL_WORDING_LANDED = (
    "That sharper wording is on the goal card, at reword — press Save wording "
    "and it's the sentence. Nothing's changed until you do, and it's yours to "
    "change only until the first proof banks against it."
)

# On the wire when the model drops the turn, and in the transcript too when it
# drops it before the first token. Those turns used to save no reply at all,
# and the refetch that ends every turn then replaced the bubble the builder
# was watching with a record of them talking to themselves. The banner
# carrying this is gone by tomorrow morning. The hole in the day isn't.
STREAM_BROKE = "Masterji lost the thread — try again."

# The workshop's three receipts, and the same argument as OFFER_LANDED above:
# a tool call is not a reason to say nothing to someone who just spoke. It is
# the room that can least afford the silence. The workshop is reachable before
# a goal exists, so this is often a builder's first exchange with the product;
# the meter counts their own rows, so the turn that bought the silence is the
# turn that spent the budget; and the thing that *did* happen landed on a panel
# beside the conversation, which they may not be looking at. Nothing about that
# turn reads as broken. It reads as being ignored.
#
# Each is streamed as a delta AND saved as the turn's content, exactly the way
# OFFER_LANDED is, so the refetch that ends the turn cannot replace the bubble
# the builder just watched arrive with a record of them talking to themselves.
#
# Count-neutral wording, because one turn may park more than one: what these
# say is the state of the pile after the turn, which is true however many calls
# built it.
PARKED_LANDED = (
    "Written down — {have} of {maximum} ideas parked, room for {left} more."
)
# The full pile gets its own sentence, because what changed at the cap is not
# the count: the room stops collecting and the only move left is choosing
# between what is on the board. prompts.PARKING_FULL says the same thing to the
# model; this is the builder's half of it.
PARKED_LANDED_FULL = (
    "Written down — that's {maximum} of {maximum} and the pile is full. "
    "Nothing more gets parked; from here it's choosing between them."
)

# The forecast's receipt. It carries what is still open for NOTES_LANDED's
# reason one room over: a count with nothing owed beside it reads as a finished
# thing, and a builder who thinks the bar is met walks into a gate nobody told
# them about. The arithmetic is bar.owed's — the same subtraction
# prompts.sketch_state does for the prompt, said to the builder instead.
SKETCH_LANDED = (
    "Filled in what a first evening's proof needs, from what you just told me "
    "— {have} of {need} parts. Still open: {owed}."
)
SKETCH_LANDED_FULL = (
    "That's all {need} parts a first evening's proof needs, already sitting in "
    "this conversation. Nothing left to sharpen in here."
)

# The title's receipt. It names the box rather than repeating the title, for
# OFFER_LANDED's reason: the title is on screen in a field the builder can
# edit, and a second copy in the chat is the one they cannot. The second
# sentence is the GOAL_EXAMPLES bargain said out loud — this room suggests, and
# committing stays a thing the builder does.
GOAL_SUGGESTED_LANDED = (
    "Put a title in the goal box — yours to edit. Committing to it is yours "
    "too; nothing here has done that for you."
)

# Said when the turns are gone. Names the exit, in the register of every other
# refusal in this file: what they have, and the one door still open.
#
# The count is interpolated, never written out in words. WORKSHOP_TURNS owns the
# number, and a refusal that spells it in prose is a second copy that goes stale
# the first time the cap moves — the same drift the gate's three number-quoting
# surfaces already cost this codebase once.
WORKSHOP_SPENT = (
    "That's the workshop done — {turns} turns, and thinking time is over. "
    "You don't need a better idea; you need one you can test. Pick the one you "
    "could ask somebody about this week, put it in the box, and commit. The "
    "first thing it asks for is one evening at your desk."
)

# The reopened room's version. Same shape and the same rule about the number,
# and a different exit, because the door out of this one is not the commit box:
# it is the three things that were always available, said once more without a
# recommendation attached.
REOPENED_SPENT = (
    "That's this room done — {turns} turns, once per goal. Nothing here changed "
    "your record and nothing was supposed to. You have the same three moves you "
    "walked in with: finish the bar in front of you, sharpen the wording, or "
    "close it today and pick again. Whichever it is, it's yours to make."
)
