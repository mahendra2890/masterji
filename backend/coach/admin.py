from django.contrib import admin
from django.utils.text import Truncator

from common.soft_delete import SoftDeleteAdmin

from .models import (
    ChangelogEntry,
    CheckIn,
    Goal,
    GoalRetirement,
    Message,
    PhaseTransition,
    ProofAttempt,
)


@admin.register(Goal)
class GoalAdmin(SoftDeleteAdmin):
    list_display = ["title", "user", "phase", "status", "is_deleted"]
    list_filter = ["phase", "status"]


@admin.register(CheckIn)
class CheckInAdmin(SoftDeleteAdmin):
    # `phase` is the row's own stamp, not the goal's current phase — a goal
    # that has moved on doesn't rewrite what its past rows belonged to.
    list_display = ["goal", "date", "phase", "proof_status", "is_deleted"]
    list_filter = ["phase", "proof_status"]


@admin.register(Message)
class MessageAdmin(SoftDeleteAdmin):
    list_display = ["goal", "phase", "role", "excerpt", "created_at", "is_deleted"]
    list_filter = ["phase", "role"]

    @admin.display(description="content")
    def excerpt(self, obj):
        """Full coach replies make the changelist unscannable; the row links
        through to the whole thing."""
        return Truncator(obj.content).chars(120)


@admin.register(GoalRetirement)
class GoalRetirementAdmin(SoftDeleteAdmin):
    list_display = [
        "goal",
        "outcome",
        "phase_reached",
        "accepted_proofs",
        "contact_proofs",
        "days_active",
        "created_at",
    ]
    list_filter = ["outcome", "phase_reached"]


@admin.register(PhaseTransition)
class PhaseTransitionAdmin(SoftDeleteAdmin):
    list_display = ["goal", "from_phase", "to_phase", "created_at"]


@admin.register(ProofAttempt)
class ProofAttemptAdmin(SoftDeleteAdmin):
    list_display = ["checkin", "excerpt", "created_at", "is_deleted"]

    @admin.display(description="text")
    def excerpt(self, obj):
        return Truncator(obj.text).chars(120)


@admin.register(ChangelogEntry)
class ChangelogEntryAdmin(SoftDeleteAdmin):
    # This is the editing surface for the changelog — writing an entry here is
    # publishing it. `is_active` is editable in the list so an entry can be
    # held back or retired without opening the row.
    list_display = ["shipped_on", "kind", "title", "is_active", "excerpt", "is_deleted"]
    list_editable = ["is_active"]
    list_filter = ["kind", "is_active"]
    search_fields = ["title", "body"]
    date_hierarchy = "shipped_on"

    @admin.display(description="body")
    def excerpt(self, obj):
        return Truncator(obj.body).chars(120)
