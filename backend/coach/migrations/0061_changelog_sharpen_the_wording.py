"""The changelog records the goal's wording being editable before anything banks.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044, 0046, 0047, 0048, 0049, 0050, 0051, 0052, 0053,
0055, 0056, 0058, 0059 and 0060: newest last, so the row created last leads its day under the
model's ("-shipped_on", "-id") ordering.

Renumbered 0057 → 0061 as four rows went in ahead of it — TRACTION's schema and
changelog, then drafts, then the paid-call ceilings. That is the collision 0052's
note predicts, four times over in one afternoon, and not once did the rebase
mention it: git has no opinion about migration graphs, which is why the leaf is
checked again immediately before the merge button.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "NEW",
        "You can sharpen the wording once you're in",
        "A goal used to be a sentence you were stuck with. Getting the wording "
        "wrong meant closing it and starting again — which zeroes the days and "
        "the streak — so the sensible thing was to sit at the commit box "
        "polishing the phrasing before starting, which is exactly the freeze "
        "that box was making worse. Now the goal card has a reword control, and "
        "the wording is yours to sharpen right up until your first proof is "
        "banked. After that it stays as it is: those evenings were filed against "
        "this goal, and renaming it then would quietly rewrite what they were "
        "for — so the choice at that point is to keep it or close it honestly. "
        "A rewording changes nothing else. It banks nothing, moves no phase, "
        "costs no days and no streak, and it goes into the conversation with "
        "both wordings named, so the record still reads straight from the top.",
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
    dependencies = [("coach", "0060_changelog_ceilings_on_the_paid_calls")]
    operations = [migrations.RunPython(seed, unseed)]
