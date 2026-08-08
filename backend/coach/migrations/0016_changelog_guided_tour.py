"""The changelog catches up with the demo becoming a guided tour.

Same shape as 0011 and 0012: newest last, so the row created last leads its
day under the model's ("-shipped_on", "-id") ordering.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 8),
        "CHANGED",
        "The demo teaches the product now",
        "It used to be one frozen screen of the app with a conversation on it, "
        "which showed what Masterji sounds like and nothing about how to use "
        "him. It's a tour now — eight steps through the real screens, with the "
        "parts that matter circled and answered in the margin: declaring in "
        "the morning, what the chat does and doesn't record, the proof he "
        "drafts out of your conversation, filing in the evening, and the gate "
        "refusing until the proofs are in. Every number and refusal in it is "
        "quoted from the code that produces it.",
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
    dependencies = [("coach", "0015_changelog_where_things_go")]
    operations = [migrations.RunPython(seed, unseed)]
