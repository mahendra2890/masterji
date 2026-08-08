from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class MasterjiUserAdmin(UserAdmin):
    list_display = ["username", "email", "tone", "mode", "is_active"]
    list_filter = ["tone", "mode", "is_active", "is_staff"]
    fieldsets = UserAdmin.fieldsets + (("Coach", {"fields": ("tone", "mode")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Coach", {"fields": ("email", "tone", "mode")}),
    )
