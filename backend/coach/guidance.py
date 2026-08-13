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

from .models import Phase

# One line under the goal title. What this phase is for, in the imperative.
PHASE_HINT = {
    Phase.IDEA: "Write the problem statement, and where you'd find these people — no outreach yet.",
    Phase.VALIDATION: "Talk to real customers. Bring notes, not opinions.",
    Phase.BUILD: "Smallest thing a real user can touch this week.",
    Phase.LAUNCH: "In front of strangers. Ask for commitment.",
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
}

# Appended to a refusal from gates.try_advance. The refusal already says what
# is missing; this says what to go and do about it tonight. It has to work
# standing alone: the dashboard's advance button hits the gate with no LLM in
# the loop, so this is the only coaching a builder gets at the exact moment
# quitting looks reasonable.
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
}


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


def for_phase(phase: Phase) -> dict:
    """The whole builder-facing bundle for one phase, for the API payload."""
    return {
        "phase_hint": PHASE_HINT[phase],
        "proof_hint": PROOF_HINT[phase],
        "proof_examples": PROOF_EXAMPLES[phase],
        "openers": OPENERS[phase],
    }
