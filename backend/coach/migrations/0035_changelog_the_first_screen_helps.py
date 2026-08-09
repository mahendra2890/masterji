"""The changelog catches up with the first screen anybody sees.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025 and 0026: newest last, so the
row created last leads its day under the model's ("-shipped_on", "-id")
ordering.

Renumbered three times while this branch was open — 0027 → 0032 → 0033 → 0035
— each time because main merged a changelog seed off the same parent this one
was written against, twice during a verification pass on this very file. That
is the normal weather here, not bad luck: every PR carries a seed and several
sessions branch off the same main. Single leaf at write time (0034).

Do the last check immediately before the merge button, not before the tests.
Two leaves stop main deploying, not just this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "The goal box says what you're agreeing to",
        "\"One goal\" — the first thing you meet after signing in — asked for "
        "the hardest decision in the product and then ended on what it would "
        "cost you to change your mind, a warning on the one screen where "
        "nobody has done anything yet to be warned about. It now says the "
        "shape of the thing instead: one task each morning, proof of it each "
        "evening, about two minutes a day. That you can close it whenever you "
        "like is still there; that he'll remember has moved to where you "
        "close it, which is where there is something to remember.",
    ),
    (
        date(2026, 8, 9),
        "NEW",
        "Three examples under the box on your first day",
        "The freeze at a blank goal box is rarely a shortage of ideas — it is "
        "not knowing how specific the answer is supposed to be, and one "
        "placeholder answers that with a single data point. There are three "
        "now, and two of them are somebody else's world on purpose: a "
        "reseller's payments, a hostel floor's notice board, a building's "
        "weekend baking orders. Tapping one fills the box for you to edit. "
        "None of them commits anything — the goal has to be yours.",
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
    dependencies = [("coach", "0034_changelog_finishing_reads_like_a_win")]
    operations = [migrations.RunPython(seed, unseed)]
