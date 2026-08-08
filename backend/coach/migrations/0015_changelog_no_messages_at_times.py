"""The changelog catches up with the turns that answered nothing.

Same shape as 0011 and 0012: newest last, so the row created last leads its
day under the model's ("-shipped_on", "-id") ordering.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 8),
        "FIXED",
        "Masterji no longer goes quiet on you",
        "Two kinds of turn used to end with your message on screen and no "
        "answer under it. One was him writing tonight's proof up from the "
        "conversation and saying nothing else — the draft landed on the Today "
        "card, which on a phone is the screen you weren't looking at, so from "
        "the chat it read as being ignored. He now says where it went, "
        "without repeating the draft itself. The other was the model dropping "
        "the turn before its first word: the red banner explaining that is "
        "gone by morning, and what was left in the record was a conversation "
        "that had answered every message except one. That line stays in the "
        "transcript now. An answer that broke off partway is still kept as "
        "far as it got.",
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
    dependencies = [("coach", "0014_merge_changelog_seeds")]
    operations = [migrations.RunPython(seed, unseed)]
