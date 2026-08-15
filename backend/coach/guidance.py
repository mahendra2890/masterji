"""Builder-facing phase copy — the words the product says on its own.

Distinct from prompts.py, which is what Masterji says *through the LLM*. This
module is the deterministic half: the stepper hint, what tonight's proof must
contain, worked examples of proofs that were accepted, and the concrete action
attached to a gate refusal. None of it depends on a model being reachable, and
all of it is the single source of truth — the dashboard reads these over the
API rather than keeping its own copy, because two copies drift and only one of
them is the one gates.py enforces.

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
