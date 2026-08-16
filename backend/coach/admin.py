from django.contrib import admin
from django.db.models import Count, Q
from django.utils.text import Truncator

from common.soft_delete import SoftDeleteAdmin

from .models import (
    ChangelogEntry,
    CheckIn,
    Cohort,
    CohortMember,
    DashboardOpen,
    Goal,
    GoalRetirement,
    LaunchCommitment,
    Message,
    ModelCall,
    PhaseTransition,
    ProofAttempt,
    Workshop,
    WorkshopMessage,
    mint_join_code,
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
    list_display = ["goal", "from_phase", "to_phase", "intent", "created_at"]


# Append-only, so the list IS the trail: several rows on one goal is a date
# that moved, and reading them in order is the whole of what this table says.
@admin.register(LaunchCommitment)
class LaunchCommitmentAdmin(SoftDeleteAdmin):
    list_display = ["goal", "date", "pond", "created_at", "is_deleted"]


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


@admin.register(Cohort)
class CohortAdmin(SoftDeleteAdmin):
    """Where a cohort comes from. There is no API route that makes one.

    That is the point rather than a gap: the whole of a coordinator's
    capability is holding a join code, so the making of a cohort is staff work
    and the product surface has no write path on it at all.
    """

    list_display = ["name", "join_code", "size", "created_at", "is_deleted"]
    search_fields = ["name", "join_code"]
    actions = ["rotate_join_code"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                member_count=Count("members", filter=Q(members__deleted_at__isnull=True))
            )
        )

    @admin.display(description="members", ordering="member_count")
    def size(self, obj):
        """Live memberships. The filter is the whole column: a reverse join
        does not inherit `SoftDeleteManager`'s predicate, so without it this
        would count everybody who ever left."""
        return obj.member_count

    @admin.action(description="Rotate join code (members keep their place)")
    def rotate_join_code(self, request, queryset):
        """Rotation IS the revocation — the old string then matches nothing,
        and closing a cohort to new joins is rotating to a code nobody has.

        It never touches members, and the description says so where the button
        is: a code is an invitation, not a session, and a rotation that ejected
        forty people would make the safe operation the dangerous one.
        """
        for cohort in queryset:
            cohort.join_code = mint_join_code()
            cohort.save(update_fields=["join_code", "updated_at"])
        self.message_user(
            request,
            f"Rotated {queryset.count()} code(s). Everyone already in stays in.",
        )


@admin.register(CohortMember)
class CohortMemberAdmin(SoftDeleteAdmin):
    # The consent, as a row. Soft-deleted ones are visible here and nowhere
    # else, which is what makes "they left" auditable without the board ever
    # showing it.
    list_display = ["cohort", "user", "joined_at", "is_deleted"]
    list_filter = ["cohort"]
    list_select_related = ["cohort", "user"]


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


@admin.register(ModelCall)
class ModelCallAdmin(SoftDeleteAdmin):
    """The operator's window onto model spend, per builder.

    Read-only on purpose: every row here is a record of something that already
    happened and was already paid for. Editing one would not un-spend it, and
    a ledger somebody can hand-correct is not evidence of anything.
    """

    list_display = [
        "created_at",
        "user",
        "kind",
        "model",
        "total_tokens",
        "cost_usd",
        "cause",
    ]
    # `source` filters to the blank option too, which is the one worth having:
    # it isolates the calls with nothing behind them — the cron, a command, a
    # shell — and the rows written before the column existed.
    list_filter = ["kind", "model", "source"]
    search_fields = ["user__username", "user__email"]
    date_hierarchy = "created_at"

    @admin.display(description="caused by")
    def cause(self, obj):
        """The two halves read as one thing, and never half of one.

        Not a link: this is a pointer rather than a foreign key, so the row it
        names may be gone, and an admin column that 500s on a pruned
        transcript would make the ledger unreadable exactly when it is being
        read about a builder who left.
        """
        if not obj.source or not obj.source_id:
            return "—"
        return f"{obj.get_source_display()} #{obj.source_id}"
    # Named here rather than as Meta.ordering — see the comment on the model
    # for why this table deliberately has no default ordering.
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        # The FK is followed on every row of the list display; without this the
        # page is one query per row, which is the exact shape #150 was filed
        # about on the dashboard.
        return super().get_queryset(request).select_related("user")


@admin.register(DashboardOpen)
class DashboardOpenAdmin(SoftDeleteAdmin):
    """A day a builder opened a live dashboard. Read-only, like the ledger.

    Registered because `AdminReachTests` requires every table in this app to
    have a reader, and this one needs it more than most: it is the only table
    here that is not a record of something the builder did, so the only way to
    see what is being kept about somebody is to look at it. `loop_report` reads
    it in aggregate; this is where you read a row.

    No add and no change, for `ModelCall`'s reason — a hand-written row would
    be a visit nobody made, and `loop_report` would print it as evidence.
    """

    list_display = ["day", "user", "created_at"]
    list_filter = ["day"]
    search_fields = ["user__username", "user__email"]
    date_hierarchy = "day"
    # Named here rather than as Meta.ordering — see the comment on the model
    # for why this table deliberately has no default ordering.
    ordering = ["-day", "user"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")
