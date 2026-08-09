"""The changelog catches up with the chat composer being four rows tall.

Same shape as 0011, 0012, 0016, 0020 and 0022: newest last, so the row created
last leads its day under the model's ("-shipped_on", "-id") ordering.

Written as 0023 off 0022 and renumbered to 0025 before the first push: main
picked up 0023_checkin_proof_missing and 0024_changelog_running_notes from a
sibling session in between, and a second 0023 off 0022 is the two-leaf graph
`migrate` refuses — which stops main deploying, not just this branch. Renamed
and re-parented onto main's leaf rather than merged, safe because this row had
never been applied anywhere but a throwaway worktree database.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "The reply box fits what you actually write",
        "The box you talk to him in was one line tall. Anything past a "
        "sentence pushed what you'd already written up out of sight, so "
        "reading your own reply back before sending it meant dragging a box "
        "the height of a single line — on the one screen where what you type "
        "runs longest, because thinking out loud is the point of it. It holds "
        "four lines now. Anything longer still scrolls, but four is what an "
        "evening's answer tends to come to, and you can see all of it at "
        "once. What counts is unchanged: nothing you say here is proof until "
        "you file it under Today.",
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
    dependencies = [("coach", "0024_changelog_running_notes")]
    operations = [migrations.RunPython(seed, unseed)]
