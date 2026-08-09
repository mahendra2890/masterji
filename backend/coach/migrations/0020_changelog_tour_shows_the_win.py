"""The changelog catches up with the tour showing the screen that says so.

Same shape as 0011, 0012 and 0016: newest last, so the row created last leads
its day under the model's ("-shipped_on", "-id") ordering.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "The tour shows the moment you've earned it",
        "The gate slide went from '2 of 3 — refused' straight to the unlocked "
        "stepper, skipping the screen in between: the bar met, and nothing "
        "pressed yet. That screen had nothing worth showing while it stayed "
        "silent. It says so now, so the tour shows it too — the counter at "
        "3/3, a full bar, and the button that hands over BUILD.",
    ),
]


def seed(apps, schema_editor):
    Entry = apps.get_model("coach", "ChangelogEntry")
    for shipped_on, kind, title, body in SEED:
        Entry.all_objects.get_or_create(
            shipped_on=shipped_on,
            title=title,
            defaults={"kind": kind, "body": body, "is_active": True},
        )


def unseed(apps, schema_editor):
    Entry = apps.get_model("coach", "ChangelogEntry")
    Entry.all_objects.filter(title__in=[title for _, _, title, _ in SEED]).delete()


class Migration(migrations.Migration):
    dependencies = [("coach", "0019_merge_two_session_changelogs")]
    operations = [migrations.RunPython(seed, unseed)]
