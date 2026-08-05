from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class MasterjiUserAdmin(UserAdmin):
    list_display = ["username", "email", "tone", "is_active"]
    list_filter = ["tone", "is_active", "is_staff"]
    fieldsets = UserAdmin.fieldsets + (("Coach", {"fields": ("tone",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Coach", {"fields": ("email", "tone")}),)
