"""The changelog catches up with the day-record work.

Two builder-visible changes shipped without a line in the product's own
record. Same shape as 0011: newest last, so the row created last leads its
day under the model's ("-shipped_on", "-id") ordering.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 8),
        "FIXED",
        "\"Today\" is your day, not the server's",
        "The daily loop has always been filed under your own date, but the "
        "dashboard read it back off the server's UTC clock. Past midnight in "
        "India that meant declaring a task and watching the empty "
        "\"Morning. One task\" form come straight back with the task "
        "sitting in the record underneath it — declaring looked like a "
        "button that does nothing. Reads and writes are on one calendar now, "
        "Masterji knows about the task on the hook at 1am, and closing a goal "
        "can no longer report fewer days active than the record shows.",
    ),
    (
        date(2026, 8, 8),
        "NEW",
        "Open a day from the record and see all of it",
        "A line in the record was a dead end: a date, the task, and a tick or "
        "a cross. The proof, the screenshot, the tries that were pushed back "
        "and what Masterji said about them were reachable from nowhere. Every "
        "row opens now — in the sidebar and in the phase drill-in — "
        "and a day opened from inside a phase closes back into it rather than "
        "dropping you out of where you were reading.",
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
    dependencies = [("coach", "0011_seed_changelog")]
    operations = [migrations.RunPython(seed, unseed)]
