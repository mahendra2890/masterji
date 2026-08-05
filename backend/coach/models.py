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
        return f"{self.title} [{self.phase}]"


class CheckIn(SoftDeleteModel):
    """One row per goal per day: the AM declaration and the PM proof."""

    class ProofStatus(models.TextChoices):
        NONE = "NONE", "No proof yet"
        ACCEPTED = "ACCEPTED", "Accepted"
        PUSHED_BACK = "PUSHED_BACK", "Pushed back"

    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="checkins")
    date = models.DateField()
    am_declaration = models.TextField(blank=True)
    pm_proof_text = models.TextField(blank=True)
    proof_url = models.URLField(blank=True)
    proof_status = models.CharField(
        max_length=12, choices=ProofStatus.choices, default=ProofStatus.NONE
    )
    coach_reaction = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["goal", "date"],
                condition=models.Q(deleted_at__isnull=True),
                name="one_checkin_per_goal_per_day",
            )
        ]

    def __str__(self):
        return f"{self.goal_id} @ {self.date}"


class Message(SoftDeleteModel):
    class Role(models.TextChoices):
        USER = "USER", "User"
        COACH = "COACH", "Coach"

    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=8, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"


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
