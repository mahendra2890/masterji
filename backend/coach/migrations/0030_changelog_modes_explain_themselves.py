"""The two modes will now say what they are, without being pressed.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026 and 0027: newest last,
so the row created last leads its day under the model's ("-shipped_on", "-id")
ordering.

Written as 0028, renumbered to 0029, renumbered again to 0030 — main merged a
sibling's seed off the same parent twice while this branch was open
(the_box_grows_as_you_type, then the_landing_is_the_door). This is the
collision every changelog seed in this app keeps hitting, and it is worth
saying plainly: the number is not yours until the merge button is pressed.

Renumbered rather than merge-migrated both times because this file had never
been applied anywhere but a dev sqlite — production has never seen it under
either old number, so there is no applied history to be inconsistent with. A
merge migration is for two seeds that are already on main.

Leaf re-checked against main at 3479b1f. Check again before merging.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "NEW",
        "The modes explain themselves now, without being pressed",
        "There was no way to find out what Think with me did except to press "
        "it — which writes the setting to every device you own — or to leave "
        "for the tour. Pressing a control to learn what it does is a dare, "
        "not a choice. \"What's the difference?\" now sits beside the switch "
        "and opens the answer in place: what each mode does to you, which "
        "half of the work each is for, that your pick follows you across "
        "devices, and that neither one moves the gate. Closed, it costs one "
        "short line.",
    ),
    (
        date(2026, 8, 9),
        "CHANGED",
        "Both mode captions say one thing each",
        "Think with me's caption ended \"The gate is unchanged\" — true, and "
        "the most important thing on that line, which is exactly why it "
        "shouldn't have been spent as a half-sentence read once in passing. "
        "It now has room in \"What's the difference?\", stated properly: "
        "proof is still the only thing that opens a phase. The captions "
        "themselves are down to naming the mode you're in.",
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
    dependencies = [("coach", "0029_changelog_the_landing_is_the_door")]
    operations = [migrations.RunPython(seed, unseed)]
