"""Soft delete, shared convention for every Masterji model.

Deletes through the API are SOFT: rows get a deleted_at stamp and vanish
from `objects` (the default manager, which every view/serializer uses).
Only Django admin — via `all_objects` — can restore or truly destroy.

Not an app: only an abstract model and an admin mixin live here, so it
needs no INSTALLED_APPS entry and generates no migrations of its own.
"""

from django.contrib import admin
from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        # bulk deletes outside admin must stay soft too
        return self.update(deleted_at=timezone.now())


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(
            deleted_at__isnull=True
        )


class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()  # default: hides soft-deleted rows
    all_objects = models.Manager()  # admin's window into everything

    class Meta:
        abstract = True
        # migrations and FK cascades must see every row
        base_manager_name = "all_objects"

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def hard_delete(self):
        """Real row removal (cascades). Admin-only by convention."""
        super().delete()

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])


class SoftDeleteAdmin(admin.ModelAdmin):
    """Admin sees every row, including soft-deleted ones, and is the ONLY
    place rows truly leave the database. The default delete buttons hard
    delete (with cascades); the "Restore" action un-deletes."""

    actions = ["restore_selected"]

    def get_queryset(self, request):
        qs = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        return qs.order_by(*ordering) if ordering else qs

    def delete_model(self, request, obj):
        obj.hard_delete()

    def delete_queryset(self, request, queryset):
        queryset.delete()  # all_objects queryset: a real bulk DELETE

    @admin.action(description="Restore selected (clear deleted)")
    def restore_selected(self, request, queryset):
        updated = queryset.update(deleted_at=None)
        self.message_user(request, f"Restored {updated} row(s).")

    @admin.display(boolean=True, description="deleted")
    def is_deleted(self, obj):
        return obj.deleted_at is not None
