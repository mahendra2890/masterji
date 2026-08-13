"""Phase gates — the part of Masterji the LLM cannot talk its way past.

Advancing a phase is a server decision: it requires N accepted proofs
earned since the goal entered its current phase. The LLM may *propose* an
advance (a function call from chat) and the dashboard has a button, but
both roads lead here, and here only the database counts.
"""

from typing import NamedTuple

from django.utils import timezone
from loguru import logger

from . import bar, guidance
from .models import CheckIn, Goal, Phase, PhaseTransition

PHASE_ORDER = [
    Phase.IDEA,
    Phase.VALIDATION,
    Phase.BUILD,
    Phase.LAUNCH,
    Phase.TRACTION,
]


class Need(NamedTuple):
    """What it takes to leave a phase, in the terms the database can check.

    `n` was the whole of this once, and a row count is the one thing a phase bar
    is not: VALIDATION's three conversations can be three conversations with the
    same willing friend, and BUILD's two artifacts can both be links nobody ever
    opened. Both are real work and neither is the evidence the phase exists to
    collect, and until the row carried WHO and WHICH PART, the only thing that
    could tell the difference was the judge prompt — which is precisely what
    this product says cannot be trusted with a gate.
    """

    n: int
    # Count distinct people rather than rows (CheckIn.subject).
    people: bool = False
    # part key -> how many of the n must carry it (CheckIn.proof_parts). Shared
    # and never mutated; a phase with no kinds requirement gets the same empty
    # mapping every time.
    kinds: dict[str, int] = {}


# Accepted proofs required to LEAVE each phase.
#
# TRACTION deliberately has no entry — see at_finish_line. It is the end of the
# ladder, and an entry there would give gate_status a next_phase to look up past
# the end of PHASE_ORDER.
PROOFS_REQUIRED = {
    Phase.IDEA: Need(n=1),  # a written problem statement + who has it
    # Three real customer conversations — with three people. The README's own
    # caption says "the person already counted cannot be counted again", and
    # this is the line that makes it true rather than hoped for.
    Phase.VALIDATION: Need(n=3, people=True),
    # A working demo + evidence someone used it. Two evenings, at least one of
    # them a real user touching the thing: the bar is any-of by design, and
    # without the kinds floor the any-of lets a builder leave BUILD having
    # shipped an artifact at a people-shaped problem, which gates.py's own
    # docstring for this phase says is the failure it is here to catch.
    Phase.BUILD: Need(n=2, kinds={"touched": 1}),
    # Three launch events, one of them a stranger acting. The count is the
    # launch-checklist ladder's one-rung-per-day, and the kind is BUILD's
    # argument one phase up: three rungs climbed is three posts, and posting is
    # not somebody acting. The phase this buys is about people who acted.
    Phase.LAUNCH: Need(n=3, kinds={"action": 1}),
}


def _banked(goal: Goal):
    """Accepted proofs stamped with the goal's CURRENT phase.

    Attribution is the check-in's stamped phase, written once when the row
    is created and never rewritten. It used to be `updated_at >=
    phase_entered_at`, which let a spent proof be recycled: re-submitting
    proof on an already-accepted row bumped auto_now `updated_at` past the
    new phase's start, so one extra click re-credited it to the phase it
    had just unlocked. A stamp can't be re-earned by touching the row.
    """
    return CheckIn.objects.filter(
        goal=goal,
        phase=goal.phase,
        proof_status=CheckIn.ProofStatus.ACCEPTED,
    )


def accepted_proofs(goal: Goal) -> int:
    """What the CURRENT phase has banked, counted the way this phase counts —
    what it takes to leave, and at LAUNCH, which has no exit to buy, whether the
    phase has produced anything at all (at_finish_line).

    Rows everywhere except VALIDATION, where it is people: three nights of notes
    about one hostelmate are three days of honest work and one person's word, and
    the phase exists to establish that more than one person has the problem.

    A BLANK subject counts as its own person. The label is the model's
    contribution and the evening's work is the builder's, so an extraction that
    came back empty must never quietly un-bank a proof that was accepted on its
    merits — the same rule proof_image_key follows, and the same rule the whole
    prompt history of this file defends.
    """
    rows = _banked(goal)
    need = PROOFS_REQUIRED.get(Phase(goal.phase))
    if need is None or not need.people:
        return rows.count()
    return (
        rows.exclude(subject="").values("subject").distinct().count()
        + rows.filter(subject="").count()
    )


def kinds_owed(goal: Goal) -> list[str]:
    """Which KINDS of evidence the current phase still has none of, named the
    way the builder was asked for them (bar.Part.label).

    Separate from accepted_proofs because it is a different question and has a
    different answer shape: "how many nights" is a number the meter can fill,
    "and one of them has to be a real user" is a sentence. Rolling the second
    into the first would show a builder 1/2 for two banked evenings, which is
    the gate lying about work that is on the record.
    """
    need = PROOFS_REQUIRED.get(Phase(goal.phase))
    if need is None or not need.kinds:
        return []
    # Counted in Python, unlike every other count in this module, and not by
    # preference: Django's JSON `contains` lookup is unsupported on SQLite, which
    # is what the tests and a local checkout run on. A gate whose arithmetic only
    # works on the production backend is a gate nobody can test, and this one is
    # bounded by the current phase's accepted check-ins — single digits, always.
    banked = list(_banked(goal).values_list("proof_parts", flat=True))
    return [
        bar.label_for(goal.phase, key)
        for key, count in need.kinds.items()
        if sum(1 for parts in banked if key in (parts or [])) < count
    ]


CONTACT_PHASES = [Phase.VALIDATION, Phase.BUILD, Phase.LAUNCH, Phase.TRACTION]
# Enough real-world contact that "this idea didn't survive testing" is a fact
# about the record rather than a flattering self-description.
INVALIDATED_AT = 2


def accepted_proofs_total(goal: Goal) -> int:
    """Every accepted proof this goal ever banked, whatever phase stamped it.

    The honest measure of work done. A builder who talked to the principal
    while still in IDEA did real work, and the phase their check-in happens to
    carry must not be used to say otherwise.
    """
    return CheckIn.objects.filter(
        goal=goal, proof_status=CheckIn.ProofStatus.ACCEPTED
    ).count()


def contact_proofs(goal: Goal) -> int:
    """Accepted proofs from VALIDATION onward.

    Used for ONE question only: does "the idea was disproved" hold up? That
    claim means real people said no, so it needs proofs from the phase whose
    entire job is talking to them. Counting IDEA write-ups here would hand a
    win label to a builder who never spoke to anyone — flattery, not accuracy.
    Nothing else asks this question: for work done, whatever the phase, use
    accepted_proofs_total; for what the phase in front of the builder has
    produced, accepted_proofs.
    """
    return CheckIn.objects.filter(
        goal=goal,
        phase__in=CONTACT_PHASES,
        proof_status=CheckIn.ProofStatus.ACCEPTED,
    ).count()


def reads_as(goal: Goal, outcome: str = "ABANDONED") -> str:
    """How the record reads when a goal closes — computed, never claimed.

    Closing is never blocked, in either direction: a builder who genuinely
    achieved their goal must be able to say so from whatever phase they were
    in, and a builder whose idea died must be able to bury it. What the server
    owns is the honest reading, from proofs the builder had to earn.

    ACHIEVED:    they finished it and there is banked work behind it — any
                 accepted proof counts, whatever phase stamped it.
    UNVERIFIED:  they say they finished with nothing accepted on the record.
                 Not an accusation — just what there is to point at.
    INVALIDATED: they made real contact and it said no. Validation working.
    UNTESTED:    dropped before the world got a vote.
    """
    if outcome == "COMPLETED":
        return "ACHIEVED" if accepted_proofs_total(goal) else "UNVERIFIED"
    return "INVALIDATED" if contact_proofs(goal) >= INVALIDATED_AT else "UNTESTED"


def at_finish_line(goal: Goal) -> bool:
    """Whether finishing is the EXPECTED move here — drives how prominent the
    control is, and nothing else. Never a gate: gating completion on the last
    phase just relocates the dead end it was meant to fix.

    Deliberately not a PROOFS_REQUIRED[TRACTION] entry either — that would give
    gate_status a next_phase to look up past the end of PHASE_ORDER and 500
    the dashboard for exactly the builders who got furthest.

    Counts the terminal phase's own proofs, not the goal's whole record. This
    read accepted_proofs_total until it was noticed that no goal can arrive at
    the end without having banked the proofs the earlier gates cost — so the
    win button lit on the first morning of a phase whose own bar had seen
    nothing, and offered the exit immediately ahead of the work that phase
    exists for. It read LAUNCH until TRACTION landed behind it, which is the
    same correction made twice: the post going out was never the finish either.
    Same count the gate uses everywhere else; the difference is only that
    TRACTION has no next phase to spend it on.
    """
    return Phase(goal.phase) is Phase.TRACTION and bool(accepted_proofs(goal))


def gate_status(goal: Goal) -> dict:
    """How far the builder is from unlocking the next phase.

    `owed` is the second half of that distance and it is carried separately on
    purpose: the dashboard promises "Earned. VALIDATION is yours to open." off
    have >= need, and a phase that then refused would be a lit door that doesn't
    open — worse than the locked door with no sign this file already worried
    about, because the builder pressed it on the product's own word.
    """
    need = PROOFS_REQUIRED.get(Phase(goal.phase))
    if need is None:  # LAUNCH — nothing left to unlock
        return {"have": 0, "need": 0, "next_phase": None, "owed": [], "banked": 0}
    idx = PHASE_ORDER.index(Phase(goal.phase))
    have = accepted_proofs(goal)
    return {
        "have": have,
        "need": need.n,
        "next_phase": PHASE_ORDER[idx + 1],
        "owed": kinds_owed(goal),
        # The rows behind `have`, which on a people-counting phase is a larger
        # number and the reason the meter appears to be ignoring banked work.
        # Carried rather than derived on the client because the client has no
        # way to compute it, and identical to `have` everywhere else by
        # definition — a phase that counts rows has nothing to explain.
        "banked": _banked(goal).count() if need.people else have,
    }


def try_advance(goal: Goal) -> tuple[bool, str]:
    """Advance if the proofs are in; otherwise say exactly what's missing."""
    status = gate_status(goal)
    if status["next_phase"] is None:
        return False, "You're at LAUNCH — there is no next phase. Ship."

    # A bare count is a locked door with no sign on it. The dashboard's advance
    # button reaches this with no LLM in the loop, so if the refusal doesn't name
    # the next action, nothing does.
    nudge = guidance.GATE_NUDGE.get(Phase(goal.phase))

    if status["have"] < status["need"]:
        missing = status["need"] - status["have"]
        if status["banked"] > status["have"]:
            # The count is people and the record is rows, and the difference is
            # invisible from the outside: a builder who filed three accepted
            # proofs and reads "1/3 accepted proofs" is being told, in the
            # product's own words, that two nights of work went missing. They
            # didn't. Say both numbers, in the order the kinds branch below
            # says its two — what is banked first, what is owed second.
            refusal = (
                f"Not yet. {status['have']}/{status['need']} in {goal.phase}: "
                f"{status['banked']} accepted proofs, "
                f"{guidance.people(status['have'])}. This phase counts people, "
                f"and the nights are banked and stay banked. What's owed is "
                f"{missing} more, {'each ' if missing > 1 else ''}someone new — "
                f"that's what {status['next_phase']} costs."
            )
        else:
            refusal = (
                f"Not yet. {status['have']}/{status['need']} accepted proofs in "
                f"{goal.phase} — {missing} more before {status['next_phase']} unlocks."
            )
        return False, f"{refusal} {nudge}" if nudge else refusal

    if status["owed"]:
        # The count is met and the kind is not. Say both, in that order: the
        # nights are banked and stay banked, and what is left is one specific
        # piece of evidence rather than more of the same.
        owed = "; ".join(status["owed"])
        refusal = (
            f"{status['have']}/{status['need']} accepted proofs in {goal.phase} "
            f"— the count is there. What isn't: {owed}. That's what "
            f"{status['next_phase']} costs."
        )
        return False, f"{refusal} {nudge}" if nudge else refusal

    from_phase = goal.phase
    goal.phase = status["next_phase"]
    goal.phase_entered_at = timezone.now()
    goal.save(update_fields=["phase", "phase_entered_at", "updated_at"])
    PhaseTransition.objects.create(
        goal=goal, from_phase=from_phase, to_phase=goal.phase
    )
    logger.info(f"Goal {goal.id} advanced {from_phase} → {goal.phase}")
    return True, f"Phase unlocked: {from_phase} → {goal.phase}."
