"""The changelog records the room before the goal.

Same shape as every changelog migration since 0011: newest last, so the row
created last leads its day under the model's ("-shipped_on", "-id") ordering.

Depends on 0062, the schema half of the same change — Workshop has to exist as
a table before the room can be described to builders.

One row, not three. The turn cap and the three-candidate ceiling are not
separate features a builder can adopt independently; they are what the room IS,
and splitting them across rows would read as three things arriving when one
thing did.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "NEW",
        "The workshop: fifteen turns before you commit",
        "Until now the first screen refused to talk. Chat, declaring and "
        "proving all need a goal, so the only thing on the no-goal screen was a "
        "box asking you to commit to something — and if you did not know what "
        "to put in it, Masterji had nothing to say until after you had already "
        "decided. There is a room there now. Fifteen turns with him before any "
        "goal exists: if you arrive with nothing he walks the last seven days of "
        "your own life for problems you already stood next to, and if you arrive "
        "with three ideas he answers that instead. He parks at most three "
        "candidates — the fourth is refused, because collecting ideas is the "
        "comfortable version of choosing one — and then the only work left is "
        "picking, on the one question that matters: which of these can you walk "
        "into a room and ask somebody about this week? Nothing in the workshop "
        "banks anything, nothing in it can advance a phase, and none of it is a "
        "prerequisite: the commit box is open the whole time and he never tells "
        "you that you are not ready. When the fifteen turns are gone, the only "
        "door left is Commit. That is on purpose — a room to think in with no "
        "end on it is just planning with better manners.",
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
    dependencies = [("coach", "0062_the_workshop")]
    operations = [migrations.RunPython(seed, unseed)]
