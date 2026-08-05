"""Phase gates — the part of Masterji the LLM cannot talk its way past.

Advancing a phase is a server decision: it requires N accepted proofs
earned since the goal entered its current phase. The LLM may *propose* an
advance (a function call from chat) and the dashboard has a button, but
both roads lead here, and here only the database counts.
"""

from django.utils import timezone
from loguru import logger

from .models import CheckIn, Goal, Phase, PhaseTransition

PHASE_ORDER = [Phase.IDEA, Phase.VALIDATION, Phase.BUILD, Phase.LAUNCH]

# Accepted proofs required to LEAVE each phase.
PROOFS_REQUIRED = {
    Phase.IDEA: 1,  # a written problem statement + who has it
    Phase.VALIDATION: 3,  # three real customer conversations
    Phase.BUILD: 2,  # a working demo + evidence someone used it
}


def accepted_proofs(goal: Goal) -> int:
    """Proofs banked toward leaving the CURRENT phase.

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
        return False, (
            f"Not yet. {status['have']}/{status['need']} accepted proofs in "
            f"{goal.phase} — {missing} more before {status['next_phase']} unlocks."
        )

    from_phase = goal.phase
    goal.phase = status["next_phase"]
    goal.phase_entered_at = timezone.now()
    goal.save(update_fields=["phase", "phase_entered_at", "updated_at"])
    PhaseTransition.objects.create(
        goal=goal, from_phase=from_phase, to_phase=goal.phase
    )
    logger.info(f"Goal {goal.id} advanced {from_phase} → {goal.phase}")
    return True, f"Phase unlocked: {from_phase} → {goal.phase}."
