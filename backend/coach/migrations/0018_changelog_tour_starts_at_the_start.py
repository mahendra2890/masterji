"""The changelog catches up with the tour learning where a builder starts.

Same shape as 0011, 0012 and 0016: newest last, so the row created last leads
its day under the model's ("-shipped_on", "-id") ordering.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "The tour starts where you start",
        "It used to open on a goal already three-quarters of the way through "
        "VALIDATION, which taught the one phase a first-time visitor is "
        "guaranteed not to be in. There's a new first step now: the screen "
        "where you commit one goal, and the first thing Masterji says back — "
        "you're in IDEA, write the problem statement and the route to those "
        "people, and you may not message anyone until VALIDATION. The evening "
        "proof also comes before the proof he drafts for you, because the "
        "shortcut only means something once you've seen the box it goes in.",
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
    dependencies = [("coach", "0017_merge_four_session_changelogs")]
    operations = [migrations.RunPython(seed, unseed)]
