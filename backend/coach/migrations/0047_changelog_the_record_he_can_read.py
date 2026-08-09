"""The changelog records Masterji reading past the current evening.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044 and 0046: newest last, so the row created last
leads its day under the model's ("-shipped_on", "-id") ordering.

Written as 0047 off 0046, main's leaf when this branch opened. Check the leaf
again immediately before the merge button rather than before the test run:
several sessions branch off the same main, one can land in between, and two
leaves stop main deploying rather than just this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 10),
        "CHANGED",
        "Masterji remembers what you already proved",
        "He has never asked you twice for something you said in the same "
        "evening — the notes he keeps under Today are exactly that promise. "
        "Earlier days were a different matter. He knew the count, \"2 of 3 "
        "accepted\", and not one word of what was in the 2, so on the fourth "
        "evening of VALIDATION he could send you back to the person you "
        "interviewed on Tuesday. Every proof he has accepted on this goal now "
        "sits in front of him while you talk: what you said, what you had "
        "declared, and which phase it was. Whatever phase it was, deliberately "
        "— a conversation you had while still in IDEA is a conversation you "
        "had, and being asked for it again because the row carries an older "
        "label was never fair. Nothing about the gate moved; he can just see "
        "the record it counts.",
    ),
    (
        date(2026, 8, 10),
        "FIXED",
        "The same proof can't count twice",
        "More than one task in a day has always been allowed, because real "
        "work counts when it happens. What nothing checked was whether it was "
        "the same work: the same conversation, filed against three cycles in "
        "one evening, banked three proofs and opened VALIDATION — the phase "
        "whose whole job is stopping exactly that. Filing words already on "
        "your record now comes straight back, naming the day it repeats, with "
        "no model in the loop to argue with. Two real conversations in one "
        "evening still count as two, and the next step on something you "
        "already showed him is not a repeat — he says what makes it new "
        "instead.",
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
    dependencies = [("coach", "0046_changelog_the_gate_waits_for_a_reading")]
    operations = [migrations.RunPython(seed, unseed)]
