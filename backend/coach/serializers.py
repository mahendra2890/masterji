from rest_framework import serializers

from . import gates
from .models import CheckIn, Goal, GoalRetirement, Message, PhaseTransition


class GoalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Goal
        fields = ["id", "title", "phase", "status", "phase_entered_at", "created_at"]
        read_only_fields = ["id", "phase", "status", "phase_entered_at", "created_at"]


class CheckInSerializer(serializers.ModelSerializer):
    class Meta:
        model = CheckIn
        fields = [
            "id",
            "date",
            "phase",
            "am_declaration",
            "pm_proof_text",
            "proof_url",
            "proof_status",
            "coach_reaction",
        ]
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at"]
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
            "title",
            "outcome",
            "reads_as",
            "reason",
            "phase_reached",
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
