"""The finish-line button says what the record already shows.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0027, 0030, 0031, 0032
and 0033: newest last, so the row created last leads its day under the model's
("-shipped_on", "-id") ordering.

Written as 0033 off 0032 and renumbered when main merged
0033_changelog_what_is_behind_goes_soft off that same parent. Single leaf at
write time (0033). Check again immediately before merging — on 2026-08-09 a
branch had to renumber twice in half an hour because sibling sessions kept
landing seeds off the same parent.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "Finishing a goal you earned now reads like a win",
        "The button for ending a goal at LAUNCH said \"Close this out\", which "
        "is what you say about a ticket. That button can only appear when your "
        "record already holds accepted proof, so it now says so: Earned. Proof "
        "is on the record — and the button reads Claim the win. Nothing about "
        "the gate moved; the words just stopped underselling the one moment "
        "the whole thing is for. The quiet \"close this goal\" link is "
        "unchanged, because it is also the way out for an idea that didn't "
        "work, and that exit stays plain.",
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
    dependencies = [("coach", "0033_changelog_what_is_behind_goes_soft")]
    operations = [migrations.RunPython(seed, unseed)]
