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
    Phase.IDEA: "Write the problem statement. List 10 people who have it — no outreach yet.",
    Phase.VALIDATION: "Talk to real customers. Bring notes, not opinions.",
    Phase.BUILD: "Smallest thing a real user can touch this week.",
    Phase.LAUNCH: "In front of strangers. Ask for commitment.",
}

# What tonight's proof has to contain. Mirrors each phase playbook's
# "What counts as PROOF for Masterji" section — kept in one place so the
# check-in form cannot promise something the playbook doesn't teach.
PROOF_HINT = {
    Phase.IDEA: (
        "What to submit: your one-paragraph problem statement, plus a list of "
        "10 real people who have this problem. Just names you could reach — "
        "you are not messaging anyone yet; conversations are VALIDATION's work."
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
PROOF_EXAMPLES = {
    Phase.IDEA: [
        "Second-year hostellers miss dinner when labs run past 21:00 — mess "
        "shuts at 21:30. They order delivery at roughly 2x menu price, or skip "
        "the meal. Ten names, Block C: Priya, Arjun, Sana, …",
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
        "and why that's bad. Then ten names — real people you could message, "
        "though you won't message anyone until VALIDATION. Desk work; one "
        "evening."
    ),
    Phase.VALIDATION: (
        "One conversation. Ten minutes, someone who already has the problem. "
        "Ask what they did the last time it happened — not whether they'd use "
        "your app. Notes tonight."
    ),
    Phase.BUILD: (
        "Put the smallest working piece in front of one person who already "
        "talked to you. A link that loads is enough."
    ),
}


def for_phase(phase: Phase) -> dict:
    """The whole builder-facing bundle for one phase, for the API payload."""
    return {
        "phase_hint": PHASE_HINT[phase],
        "proof_hint": PROOF_HINT[phase],
        "proof_examples": PROOF_EXAMPLES[phase],
    }
