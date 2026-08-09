"""Popups blur what is behind them instead of flattening it to a tint.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0027, 0030, 0031 and
0032: newest last, so the row created last leads its day under the model's
("-shipped_on", "-id") ordering.

Single leaf at write time (0032). Check again immediately before merging — on
2026-08-09 a branch had to renumber twice in half an hour because sibling
sessions kept landing seeds off the same parent.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "A popup blurs your board instead of blacking it out",
        "Opening a day, a phase or What's new dropped a flat dark sheet over "
        "the dashboard, and the work you opened it from stopped existing for "
        "as long as you read. The sheet now blurs what's behind it instead: "
        "your goal, today's declaration and the record stay legible as shape "
        "and colour, so the record you're reading still reads as a detail of "
        "your board rather than a screen of its own. The sign-in popup has "
        "worked this way since it shipped; every popup now does.",
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
    dependencies = [("coach", "0032_changelog_the_return_key_makes_a_line")]
    operations = [migrations.RunPython(seed, unseed)]
