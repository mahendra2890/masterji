"""The caption under the mode switch drops the half nobody could act on.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025 and 0026: newest last, so the
row created last leads its day under the model's ("-shipped_on", "-id")
ordering.

Single leaf at write time (0026). Check again before merging — sessions have
collided on this file repeatedly, and two leaves stop main deploying rather
than just this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "FIXED",
        "The line under the mode switch stops telling you to switch",
        "Under Coach me it read \"Assignments and push-back. Switch before "
        "there's anything to declare.\" Switch to what — the other option is "
        "already sitting right there, named. And it read as a deadline the "
        "control has never had: you can change modes whenever you like, "
        "including after today's task is declared. It also spent a word the "
        "screen was already spending, because the line under the same box "
        "says \"Declare today's task under Today first\" when you have "
        "nothing declared — two \"declare\"s two inches apart, one of them "
        "something you could act on. The caption now says what the mode "
        "you're in does and stops. What Think with me is for takes a "
        "paragraph, and the tour has one.",
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
    dependencies = [("coach", "0026_changelog_notes_earn_their_place")]
    operations = [migrations.RunPython(seed, unseed)]
