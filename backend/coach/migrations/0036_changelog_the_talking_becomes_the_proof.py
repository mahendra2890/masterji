"""The changelog catches up with the note under the reply box.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026 and 0035: newest last,
so the row created last leads its day under the model's ("-shipped_on", "-id")
ordering.

Single leaf at write time (0035). Check it again immediately before the merge
button, not just before the tests — every PR here carries a seed and several
sessions branch off the same main, so the collision arrives while the branch
is open rather than while it is being written. Two leaves stop main deploying,
not just this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "The note under the reply box gives credit before the rule",
        "\"Nothing here counts\" led the line under the composer, and alone at "
        "the front of a sentence it read as don't bother typing — at the exact "
        "moment you were telling him what you'd done all evening. It was also "
        "false: the draft that turns up under Today is written from that box "
        "and nowhere else. The rule has not moved an inch, it just goes "
        "second now. Once today's task is declared the line says he writes "
        "tonight's proof from this conversation, and that nothing counts "
        "until you file it under Today. Before you've declared it promises "
        "the draft instead of claiming it — with no task to hang notes on, "
        "he genuinely isn't taking any yet.",
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
    dependencies = [("coach", "0035_changelog_the_first_screen_helps")]
    operations = [migrations.RunPython(seed, unseed)]
