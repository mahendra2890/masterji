from django.contrib import admin

from common.soft_delete import SoftDeleteAdmin

from .models import CheckIn, Goal, Message, PhaseTransition


@admin.register(Goal)
class GoalAdmin(SoftDeleteAdmin):
    list_display = ["title", "user", "phase", "status", "is_deleted"]
    list_filter = ["phase", "status"]


@admin.register(CheckIn)
class CheckInAdmin(SoftDeleteAdmin):
    list_display = ["goal", "date", "proof_status", "is_deleted"]
    list_filter = ["proof_status"]


@admin.register(Message)
class MessageAdmin(SoftDeleteAdmin):
    list_display = ["goal", "role", "content", "created_at", "is_deleted"]
    list_filter = ["role"]


@admin.register(PhaseTransition)
class PhaseTransitionAdmin(SoftDeleteAdmin):
    list_display = ["goal", "from_phase", "to_phase", "created_at"]
