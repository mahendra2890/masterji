"""The mode disclosure shipped this morning and comes back out this morning.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0027 and 0030: newest
last, so the row created last leads its day under the model's
("-shipped_on", "-id") ordering.

Single leaf at write time (0030). Check again immediately before merging — on
2026-08-09 a branch had to renumber twice in half an hour because sibling
sessions kept landing seeds off the same parent.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "The mode switch is a control again, not a help page",
        "\"What's the difference?\" lasted one release. It put a third piece "
        "of text in a bar that already held the switch and a caption, and "
        "three things reading for attention in one strip is clutter however "
        "useful the third one is. The row is back to the two modes and one "
        "line about the one you're in. What Think with me is for is explained "
        "in the tour, at the length it actually takes.",
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
    dependencies = [("coach", "0030_changelog_modes_explain_themselves")]
    operations = [migrations.RunPython(seed, unseed)]
