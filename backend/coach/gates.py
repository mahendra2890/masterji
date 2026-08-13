"""Phase gates — the part of Masterji the LLM cannot talk its way past.

Advancing a phase is a server decision: it requires N accepted proofs
earned since the goal entered its current phase. The LLM may *propose* an
advance (a function call from chat) and the dashboard has a button, but
both roads lead here, and here only the database counts.
"""

from django.utils import timezone
from loguru import logger

from . import guidance
from .models import CheckIn, Goal, Phase, PhaseTransition

PHASE_ORDER = [Phase.IDEA, Phase.VALIDATION, Phase.BUILD, Phase.LAUNCH]

# Accepted proofs required to LEAVE each phase.
PROOFS_REQUIRED = {
    Phase.IDEA: 1,  # a written problem statement + who has it
    Phase.VALIDATION: 3,  # three real customer conversations
    Phase.BUILD: 2,  # a working demo + evidence someone used it
}


def accepted_proofs(goal: Goal) -> int:
    """Proofs banked in the CURRENT phase — what it takes to leave, and at
    LAUNCH, which has no exit to buy, whether the phase has produced anything
    at all (at_finish_line).

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
    ).count()


CONTACT_PHASES = [Phase.VALIDATION, Phase.BUILD, Phase.LAUNCH]
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
    control is, and nothing else. Never a gate: gating completion on LAUNCH
    just relocates the dead end it was meant to fix.

    Deliberately not a PROOFS_REQUIRED[LAUNCH] entry either — that would give
    gate_status a next_phase to look up past the end of PHASE_ORDER and 500
    the dashboard for exactly the builders who got furthest.

    Counts LAUNCH's own proofs, not the goal's whole record. This read
    accepted_proofs_total until it was noticed that no goal can arrive at
    LAUNCH without having banked the six proofs the earlier gates cost — so
    the win button lit on the first morning of the phase, before the post went
    out, and offered the exit immediately ahead of the one piece of work the
    phase exists for. Same count the gate uses everywhere else; the difference
    is only that LAUNCH has no next phase to spend it on.
    """
    return Phase(goal.phase) is Phase.LAUNCH and bool(accepted_proofs(goal))


def gate_status(goal: Goal) -> dict:
    """How far the builder is from unlocking the next phase."""
    need = PROOFS_REQUIRED.get(Phase(goal.phase))
    if need is None:  # LAUNCH — nothing left to unlock
        return {"have": 0, "need": 0, "next_phase": None}
    idx = PHASE_ORDER.index(Phase(goal.phase))
    return {
        "have": accepted_proofs(goal),
        "need": need,
        "next_phase": PHASE_ORDER[idx + 1],
    }


def try_advance(goal: Goal) -> tuple[bool, str]:
    """Advance if the proofs are in; otherwise say exactly what's missing."""
    status = gate_status(goal)
    if status["next_phase"] is None:
        return False, "You're at LAUNCH — there is no next phase. Ship."

    if status["have"] < status["need"]:
        missing = status["need"] - status["have"]
        refusal = (
            f"Not yet. {status['have']}/{status['need']} accepted proofs in "
            f"{goal.phase} — {missing} more before {status['next_phase']} unlocks."
        )
        # A bare count is a locked door with no sign on it. The dashboard's
        # advance button reaches this with no LLM in the loop, so if the
        # refusal doesn't name the next action, nothing does.
        nudge = guidance.GATE_NUDGE.get(Phase(goal.phase))
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
