from rest_framework import serializers

from .models import CheckIn, Goal, Message, PhaseTransition


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


class PhaseTransitionSerializer(serializers.ModelSerializer):
    """Phase boundaries — the frontend derives each phase's date window
    from these plus the goal's created_at, to power the stepper drill-in."""

    class Meta:
        model = PhaseTransition
        fields = ["from_phase", "to_phase", "created_at"]
        read_only_fields = fields
