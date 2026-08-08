"""Changelog row for the mode control moving out of the header.

Named for its subject rather than numbered into the queue on purpose: three
other branches in flight each add their own 0015, and 0014 exists because two
0012s did the same thing and stopped the deploy. A distinct name makes the
clash visible in the diff instead of at `migrate` time; whichever of these
lands second wants the same treatment 0014 gave the 0012s — a merge migration
naming both leaves, not a re-parenting.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 8),
        "CHANGED",
        "The two ways of talking are visible now",
        "Masterji has always had a second way of talking — a thinking "
        "partner, for the part of the work that comes before there is "
        "anything to declare. You would have had no way of knowing. It was a "
        "single button in the top corner reading 'Coach', which told you the "
        "mode you were already in and left you to guess that pressing it "
        "offered a different one, and it lived in the strip with your "
        "username and the sign-out link, where nobody looks for a way of "
        "talking. On a phone the whole explanation was a hover tooltip, on a "
        "screen that has no hover. It now sits above the box you type in, as "
        "two options with the live one lit: Coach me, or Think with me. The "
        "line under it says what each one does. What has not changed is the "
        "part that matters: the gate never read this setting and still "
        "doesn't. Thinking out loud with Masterji was never a way around the "
        "door, and asking him to do it costs you nothing.",
    ),
]


def seed(apps, schema_editor):
    Entry = apps.get_model("coach", "ChangelogEntry")
    for shipped_on, kind, title, body in reversed(SEED):
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
