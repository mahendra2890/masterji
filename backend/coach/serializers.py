from rest_framework import serializers

from .models import CheckIn, Goal, Message


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
