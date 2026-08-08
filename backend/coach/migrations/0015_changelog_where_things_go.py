"""The changelog catches up with the two-boxes work.

Same shape as 0011 and 0012: newest last, so the row created last leads its
day under the model's ("-shipped_on", "-id") ordering.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 8),
        "FIXED",
        "Masterji now says which box counts",
        "Two text boxes, the same free text, and nothing anywhere saying that "
        "only one of them reaches the gate — so the commonest way to lose an "
        "evening was to describe real work in the chat and file nothing. The "
        "chat says what it is now, and keeps saying it under the composer "
        "after the placeholder has gone. Wherever the product tells you where "
        "to file, it says \"Today\" instead of pointing: \"above\" was the "
        "left-hand column on a laptop and a tab you couldn't see on a phone.",
    ),
    (
        date(2026, 8, 8),
        "CHANGED",
        "A proof he drafted for you is harder to miss",
        "When Masterji writes tonight's proof out of your conversation, the "
        "Today tab now says so in a word rather than showing the same dot it "
        "has shown since the day started — on a phone the draft was landing "
        "on the screen you weren't looking at, with nothing to say it had "
        "arrived. And if he drafts one before you've declared a task, he "
        "hands it back to you in the chat with the reason instead of dropping "
        "it: the work behind it was yours, so the writing-up is too.",
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
