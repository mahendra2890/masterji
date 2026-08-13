from rest_framework import serializers

from . import gates, storage
from .models import (
    ChangelogEntry,
    CheckIn,
    Goal,
    GoalRetirement,
    Message,
    PhaseTransition,
    ProofAttempt,
)


class GoalSerializer(serializers.ModelSerializer):
    # Whether the wording is still the builder's to sharpen. The same count the
    # view checks before allowing it (gates.accepted_proofs_total), sent so the
    # dashboard offers the control exactly while it would be accepted — an edit
    # affordance that appears and then 409s is worse than one that was never
    # there.
    title_locked = serializers.SerializerMethodField()

    class Meta:
        model = Goal
        fields = [
            "id",
            "title",
            "phase",
            "status",
            "phase_entered_at",
            "created_at",
            "title_locked",
        ]
        # Everything except the title. `phase` and `status` being read-only here
        # is what stops the update endpoint from being a road around the gate —
        # a PATCH may reword a goal and may never advance one.
        read_only_fields = [
            "id",
            "phase",
            "status",
            "phase_entered_at",
            "created_at",
            "title_locked",
        ]

    def get_title_locked(self, obj: Goal) -> bool:
        return gates.accepted_proofs_total(obj) > 0


class ProofAttemptSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProofAttempt
        fields = ["id", "text", "url", "image_url", "reaction", "created_at"]
        read_only_fields = fields

    def get_image_url(self, obj: ProofAttempt) -> str:
        if not obj.image_key or not storage.is_configured():
            return ""
        return storage.view_url(obj.image_key)


class CheckInSerializer(serializers.ModelSerializer):
    # The pushed-back tries behind this check-in's current proof, oldest
    # first. Callers serializing many rows should prefetch "attempts".
    attempts = ProofAttemptSerializer(many=True, read_only=True)
    # Signed on read, never stored: the bucket is private and these links
    # expire in minutes, so a proof image can't leak by being pasted anywhere.
    proof_image_url = serializers.SerializerMethodField()

    class Meta:
        model = CheckIn
        fields = [
            "id",
            "date",
            "phase",
            "am_declaration",
            "declaration_fit",
            "declaration_reaction",
            "proof_ask",
            "proof_offer",
            "proof_missing",
            "pm_proof_text",
            "proof_url",
            "proof_image_url",
            "proof_status",
            "coach_reaction",
            "attempts",
        ]
        read_only_fields = fields

    def get_proof_image_url(self, obj: CheckIn) -> str:
        if not obj.proof_image_key or not storage.is_configured():
            return ""
        return storage.view_url(obj.proof_image_key)


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        # `phase` has been stamped on every row since the model had the field,
        # and was never sent. The client needs it to tell "this builder has
        # said nothing in the phase they are in now" from "this log is empty",
        # which is what decides whether the phase's opening questions are worth
        # offering — see the openers in app/Masterji.tsx.
        fields = ["id", "role", "content", "phase", "created_at"]
        read_only_fields = fields


class RetirementSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="goal.title", read_only=True)
    # Computed from earned proofs, never stored and never client-settable, so
    # it can't drift or be forged into a flattering label.
    reads_as = serializers.SerializerMethodField()

    class Meta:
        model = GoalRetirement
        fields = [
            "id",
            "goal",  # the closed goal's id, for fetching its day-by-day record
            "title",
            "outcome",
            "reads_as",
            "reason",
            "phase_reached",
            "accepted_proofs",
            "contact_proofs",
            "days_active",
            "best_streak",
            "coach_reaction",
            "created_at",
        ]
        read_only_fields = fields

    def get_reads_as(self, obj) -> str:
        return gates.reads_as(obj.goal, obj.outcome)


class PhaseTransitionSerializer(serializers.ModelSerializer):
    """Phase boundaries — the frontend derives each phase's date window
    from these plus the goal's created_at, to power the stepper drill-in."""

    class Meta:
        model = PhaseTransition
        fields = ["from_phase", "to_phase", "created_at"]
        read_only_fields = fields


class ChangelogEntrySerializer(serializers.ModelSerializer):
    """Read-only, and public: this is the one payload here that isn't scoped
    to a user, so it carries nothing but the entry itself."""

    class Meta:
        model = ChangelogEntry
        fields = ["id", "shipped_on", "kind", "title", "body"]
        read_only_fields = fields
