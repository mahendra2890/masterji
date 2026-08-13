from django.contrib import admin
from django.db.models import Count, Q
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
    Workshop,
    WorkshopMessage,
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


class WorkshopMessageInline(admin.TabularInline):
    """The idea discussion, in order, on the room it happened in.

    The only inline in this file, and it earns the exception. Every other
    transcript here has a second reader: a goal's chat is on screen in the
    product for as long as the goal lives. This one has none — the room is
    spent by the commit it was for and leaves the no-goal screen, so after a
    builder finally picks something, the conversation that got them there is
    visible in this admin and nowhere else. Reassembling it from a filtered
    changelist is not reading it.

    Read-only on purpose. This is a record of what was said, and a place you
    scroll through to read a conversation is a place where a stray keystroke
    rewrites one. The changelist below is where a row can still be edited.
    """

    model = WorkshopMessage
    extra = 0
    can_delete = False
    fields = ["role", "content", "created_at", "deleted_at"]
    readonly_fields = ["role", "content", "created_at", "deleted_at"]

    class Media:
        # One rule, and it is about this inline only — see the file.
        css = {"all": ("coach/css/admin_transcript.css",)}

    def get_queryset(self, request):
        # SoftDeleteAdmin's window, which an inline does not inherit: a formset
        # goes through the default manager, and that one hides soft-deleted
        # rows. A transcript with a silent hole in it is worse than no
        # transcript — `deleted_at` is a column above so the hole is marked.
        return self.model.all_objects.get_queryset()

    def has_add_permission(self, request, obj):
        return False


@admin.register(Workshop)
class WorkshopAdmin(SoftDeleteAdmin):
    """The room before the goal — and where the idea discussions are read."""

    list_display = [
        "user",
        "status",
        "turns",
        "parked",
        "suggested_title",
        "created_at",
        "is_deleted",
    ]
    list_filter = ["status"]
    list_select_related = ["user"]
    inlines = [WorkshopMessageInline]

    def get_queryset(self, request):
        # Annotated rather than counted per row: `turns` is the column you scan
        # the whole page for, and a property would be one query per row.
        return (
            super()
            .get_queryset(request)
            .annotate(
                _turns=Count(
                    "messages",
                    filter=Q(
                        messages__role=WorkshopMessage.Role.USER,
                        messages__deleted_at__isnull=True,
                    ),
                )
            )
        )

    @admin.display(description="turns used", ordering="_turns")
    def turns(self, obj):
        """What the room has spent of its budget — views._turns_used, as a
        column. USER rows only: the coach's half of a conversation is not
        something the builder was charged for. This is the number that says
        whether a SPENT room ran out of turns or was spent by a commit."""
        return obj._turns

    @admin.display(description="parked")
    def parked(self, obj):
        """The candidates, at most three by construction (MAX_CANDIDATES)."""
        return Truncator("; ".join(obj.candidates or [])).chars(120)


@admin.register(WorkshopMessage)
class WorkshopMessageAdmin(SoftDeleteAdmin):
    # The cross-room view of the same rows: every idea discussion in one list,
    # the way MessageAdmin reads for goals. `user` is here because
    # Workshop.__str__ is an id and a status — true of the room, and no help at
    # all when the question is whose conversation this was.
    list_display = ["workshop", "user", "role", "excerpt", "created_at", "is_deleted"]
    list_filter = ["role"]
    list_select_related = ["workshop__user"]

    @admin.display(description="user")
    def user(self, obj):
        return obj.workshop.user

    @admin.display(description="content")
    def excerpt(self, obj):
        return Truncator(obj.content).chars(120)


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
