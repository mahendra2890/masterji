"""Masterji's state machine lives in these rows, not in the LLM.

A user has at most ONE active goal (database constraint — the product
thesis is one thing at a time). The goal walks IDEA → VALIDATION → BUILD →
LAUNCH, and every transition is earned with accepted proofs (see gates.py).
Check-ins are the daily declare-AM / prove-PM loop; messages are the chat
transcript. Tenancy rule: views filter by request.user, so foreign ids 404.
"""

from django.conf import settings
from django.db import models

from common.soft_delete import SoftDeleteModel


class Phase(models.TextChoices):
    IDEA = "IDEA", "Idea"
    VALIDATION = "VALIDATION", "Validation"
    BUILD = "BUILD", "Build"
    LAUNCH = "LAUNCH", "Launch"


class Goal(SoftDeleteModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        ABANDONED = "ABANDONED", "Abandoned"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals"
    )
    title = models.CharField(max_length=200)
    phase = models.CharField(max_length=12, choices=Phase.choices, default=Phase.IDEA)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    # Proofs only count toward the gate if earned in the current phase.
    phase_entered_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(SoftDeleteModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="ACTIVE", deleted_at__isnull=True),
                name="one_active_goal_per_user",
            )
        ]

    def __str__(self):
        # Title only — deliberately no phase. This label renders wherever a
        # goal is referenced, including rows written phases ago, and mutable
        # state in it reads as history being rewritten: a message sent during
        # IDEA would show "[VALIDATION]" once the goal moved on. Per-row phase
        # lives on the rows themselves (CheckIn.phase, Message.phase).
        return self.title


class CheckIn(SoftDeleteModel):
    """One declare→prove cycle: the task claimed, and the proof of it.

    Usually one a day (the habit the coach is building), but a builder who
    genuinely does more in a day may run more cycles — real work counts
    when it happens. Only ONE may be open at a time per day, so there is
    always exactly one task on the hook; Masterji does the pacing in
    conversation, not by silently declining to count what you did.
    """

    class ProofStatus(models.TextChoices):
        NONE = "NONE", "No proof yet"
        ACCEPTED = "ACCEPTED", "Accepted"
        PUSHED_BACK = "PUSHED_BACK", "Pushed back"

    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="checkins")
    date = models.DateField()
    # The phase this day's work belonged to, stamped when the row is created.
    # `date` can't be used to infer it: dates come from the CLIENT's local
    # clock while phase transitions are recorded in server UTC, so around a
    # late-night advance the two disagree about which day it is.
    phase = models.CharField(max_length=12, choices=Phase.choices, blank=True)
    am_declaration = models.TextField(blank=True)
    # Whether this morning's task is the work this phase is actually for.
    # Advisory, never a veto: the builder may do whatever they declared, and
    # a task judged off-phase still earns its proof. UNJUDGED is the honest
    # state when the model was unreachable — not a silent "fine".
    class DeclarationFit(models.TextChoices):
        UNJUDGED = "UNJUDGED", "Not judged"
        ON_PHASE = "ON_PHASE", "On phase"
        OFF_PHASE = "OFF_PHASE", "Off phase"

    declaration_fit = models.CharField(
        max_length=12, choices=DeclarationFit.choices, default=DeclarationFit.UNJUDGED
    )
    declaration_reaction = models.TextField(blank=True)
    # What tonight's proof must show FOR THIS TASK. Falls back to the phase's
    # static ask (guidance.PROOF_HINT) when empty, so the form is never blank.
    proof_ask = models.TextField(blank=True)
    pm_proof_text = models.TextField(blank=True)
    proof_url = models.URLField(blank=True)
    # Opaque object-storage key for a screenshot backing tonight's proof.
    # Corroboration, never the proof itself: a failed upload must not cost the
    # builder their check-in, so this stays blank and the text still counts.
    proof_image_key = models.CharField(max_length=200, blank=True)
    proof_status = models.CharField(
        max_length=12, choices=ProofStatus.choices, default=ProofStatus.NONE
    )
    coach_reaction = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["-date"]
        constraints = [
            # Many finished cycles a day are fine; two OPEN ones are not —
            # that would mean two tasks on the hook at once, and it makes a
            # double-tapped "Declare it" idempotent.
            models.UniqueConstraint(
                fields=["goal", "date"],
                condition=models.Q(deleted_at__isnull=True, pm_proof_text=""),
                name="one_open_checkin_per_goal_per_day",
            )
        ]

    def __str__(self):
        return f"{self.goal_id} @ {self.date}"


class GoalRetirement(SoftDeleteModel):
    """A goal's last words, written when it stops being active.

    The numbers are a SNAPSHOT taken at retirement, not a live query. Re-deriving
    them later would read today's state onto a historical row — the same mistake
    CheckIn.phase and Goal.__str__ already carry comments about.

    Nothing here is a self-assigned verdict. The builder writes prose; whether
    the idea was actually tested is computed from proofs they had to earn
    (gates.reads_as), because a flaker asked to classify their own exit will
    always pick the flattering label.
    """

    class Outcome(models.TextChoices):
        ABANDONED = "ABANDONED", "Abandoned"
        COMPLETED = "COMPLETED", "Completed"

    goal = models.OneToOneField(
        Goal, on_delete=models.CASCADE, related_name="retirement"
    )
    outcome = models.CharField(max_length=12, choices=Outcome.choices)
    reason = models.TextField()
    phase_reached = models.CharField(max_length=12, choices=Phase.choices)
    # Every accepted proof, whatever phase stamped it — what the builder
    # actually banked, and what the archive shows them.
    accepted_proofs = models.PositiveIntegerField(default=0)
    # The VALIDATION-onward subset. Narrower on purpose, and used for exactly
    # one thing: whether "the idea was disproved" holds up. That claim means
    # real people said no, so IDEA write-ups can't buy it.
    contact_proofs = models.PositiveIntegerField(default=0)
    days_active = models.PositiveIntegerField(default=0)
    best_streak = models.PositiveIntegerField(default=0)
    coach_reaction = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.goal_id}: {self.outcome}"


class Message(SoftDeleteModel):
    class Role(models.TextChoices):
        USER = "USER", "User"
        COACH = "COACH", "Coach"

    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=8, choices=Role.choices)
    content = models.TextField()
    # The phase the conversation was in, stamped once. Reading it off the goal
    # instead would report today's phase for a message sent weeks ago.
    phase = models.CharField(max_length=12, choices=Phase.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"


class ProofAttempt(SoftDeleteModel):
    """A proof submission Masterji pushed back, preserved when the builder
    answers it with a new one.

    The check-in's own proof fields always hold the CURRENT submission; this
    table is the trail of the tries before it. Written archive-before-
    overwrite in the prove view, so the happy path (first proof accepted)
    never creates a row. Every row here is by construction a pushed-back try
    — an accepted proof closes the cycle and can never be overwritten.

    This table is also what keeps evidence honestly attributed: before it
    existed, a resubmission overwrote the text but left the old image key on
    the check-in, so an accepted proof could end up wearing the screenshot
    of the rejected try.
    """

    checkin = models.ForeignKey(
        CheckIn, on_delete=models.CASCADE, related_name="attempts"
    )
    text = models.TextField()
    url = models.URLField(blank=True)
    image_key = models.CharField(max_length=200, blank=True)
    reaction = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["created_at"]

    def __str__(self):
        return f"pushed-back try on {self.checkin_id}"


class PhaseTransition(SoftDeleteModel):
    goal = models.ForeignKey(
        Goal, on_delete=models.CASCADE, related_name="transitions"
    )
    from_phase = models.CharField(max_length=12, choices=Phase.choices)
    to_phase = models.CharField(max_length=12, choices=Phase.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.goal_id}: {self.from_phase} → {self.to_phase}"
