from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from loguru import logger

from . import impersonation
from .cookies import set_impersonation_cookie
from .models import Impersonation, User


@admin.register(User)
class MasterjiUserAdmin(UserAdmin):
    list_display = ["username", "email", "mode", "is_active", "view_as"]
    list_filter = ["mode", "is_active", "is_staff"]
    fieldsets = UserAdmin.fieldsets + (("Coach", {"fields": ("mode",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Coach", {"fields": ("email", "mode")}),
    )

    def get_urls(self):
        return [
            path(
                "<int:user_id>/impersonate/",
                # `admin_view` is the gate and it is the whole gate: staff
                # only, and an anonymous caller is sent to the admin's own
                # login — which is the throttled one
                # (AdminLoginThrottleMiddleware), and the only password in
                # this deployment.
                self.admin_site.admin_view(self.impersonate_view),
                name="accounts_user_impersonate",
            ),
            *super().get_urls(),
        ]

    @admin.display(description="view as")
    def view_as(self, obj):
        if not _may_impersonate(obj):
            return "—"
        url = reverse("admin:accounts_user_impersonate", args=[obj.pk])
        return format_html('<a href="{}">View as</a>', url)

    def impersonate_view(self, request, user_id):
        """Confirm, then hand this browser a read-only session as `target`.

        GET is a confirmation page rather than a link that acts, because this
        is a state change on the browser that makes it: one stray click in a
        changelist should not silently swap whose account is on screen.
        The form is a real admin form, so Django's CSRF protection covers the
        POST without anything here arranging it.
        """
        target = get_object_or_404(User, pk=user_id)
        refusal = _why_not(request.user, target)

        if request.method != "POST":
            return TemplateResponse(
                request,
                "admin/accounts/user/impersonate.html",
                {
                    **self.admin_site.each_context(request),
                    "title": f"View as {target.username}",
                    "target": target,
                    "refusal": refusal,
                    "minutes": settings.IMPERSONATION_LIFETIME_S // 60,
                    "opts": self.model._meta,
                },
            )

        if refusal:
            # Re-checked on POST rather than trusted from the GET: the two are
            # separate requests, and `is_staff` can be granted in between.
            self.message_user(request, refusal, messages.ERROR)
            return HttpResponseRedirect(
                reverse("admin:accounts_user_changelist")
            )

        token = impersonation.issue(request.user, target)
        Impersonation.objects.create(
            operator=request.user,
            target=target,
            expires_at=timezone.now() + impersonation.lifetime(),
        )
        # A log line as well as the row, because the row is only reachable by
        # somebody who already suspects; this reaches whoever is reading the
        # deployment's logs without being asked.
        logger.info(
            "impersonation start operator={} target={} minutes={}",
            request.user.get_username(),
            target.pk,
            settings.IMPERSONATION_LIFETIME_S // 60,
        )
        response = HttpResponseRedirect(settings.FRONTEND_URL)
        set_impersonation_cookie(
            response, token, max_age=settings.IMPERSONATION_LIFETIME_S
        )
        return response


def _may_impersonate(target) -> bool:
    return not target.is_staff and not target.is_superuser and target.is_active


def _why_not(operator, target) -> str | None:
    """Why this pair is refused, in the operator's own words, or None.

    A string rather than a boolean because the refusal is shown, and "no"
    without a reason on an operator tool is how somebody ends up reaching for
    the shell instead.
    """
    if target.pk == operator.pk:
        return "That is your own account."
    if target.is_staff or target.is_superuser:
        return (
            "Operator accounts cannot be viewed this way. Impersonating one "
            "would be a way to borrow its admin access, which the read-only "
            "rule does not cover — it guards the API, not this site."
        )
    if not target.is_active:
        return (
            "This account is inactive — erased, or disabled. Its tokens are "
            "refused at authentication, so the session would not work anyway."
        )
    return None


@admin.register(Impersonation)
class ImpersonationAdmin(admin.ModelAdmin):
    """Read-only, including for a superuser, because it is the record of what
    a superuser did. Rows are written by `impersonate_view` and by nothing
    else; an admin that could add one would be an admin that could forge one,
    and one that could edit one would make the whole log worth less than the
    trouble of keeping it."""

    list_display = ["started_at", "operator", "target", "expires_at"]
    list_filter = ["operator"]
    date_hierarchy = "started_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
