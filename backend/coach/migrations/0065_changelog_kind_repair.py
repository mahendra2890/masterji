"""Repairs the TRACTION row's kind, and records the repair.

Two operations, because this migration is both halves of one bug: the row 0058
wrote is wrong in every database that has run it, and the fix is a change
builders can see in What's New.

0058 seeded its first row with kind "ADDED", which is not in
ChangelogEntry.Kind (NEW / CHANGED / FIXED / METHOD). Django does not validate
choices on write and a data migration never reaches full_clean, so it shipped.
components/Changelog.tsx looks the label up in a total map — KIND_LABEL[e.kind]
came back undefined and styles["added"] with it — so the newest capability the
product had shipped wore a chip with no text and no styling, second from the top
of the list every builder sees when they open What's New.

Repaired rather than rewritten in place: 0058 has already run everywhere, so
editing it would fix nothing that exists. Matched on title, which is the same
key its own get_or_create used.

The guard is in the test suite rather than here —
test_every_seeded_kind_is_one_the_frontend_can_render asserts over the rows a
migrated database holds, which is what the frontend actually gets.
"""

from datetime import date

from django.db import migrations

BROKEN_TITLE = "TRACTION: the phase after the post"

SEED = [
    (
        date(2026, 8, 13),
        "FIXED",
        "The newest What's New entry gets its label back",
        "The entry announcing TRACTION went in with a label this app has no "
        "name for, so it rendered as a blank chip — no word, no colour — on the "
        "one list whose whole job is telling you what changed. It reads \"new\" "
        "now, like every other entry that added something. Nothing about the "
        "phase itself changed. Shipping alongside it: at TRACTION the coach was "
        "being handed your proof count as zero, whatever you had actually "
        "banked there, because the last phase has no gate to count toward and "
        "the code took that to mean there was nothing to count. It reads the "
        "record now. Only the coach's copy of the number was wrong — every "
        "proof you filed was banked correctly, and the finish line has always "
        "lit off the real one.",
    ),
]


def repair(apps, schema_editor):
    Entry = apps.get_model("coach", "ChangelogEntry")
    Entry.all_objects.filter(title=BROKEN_TITLE, kind="ADDED").update(kind="NEW")


def unrepair(apps, schema_editor):
    """Puts the invalid kind back, because that is what reversing this means.

    A reverse that left NEW in place would make this migration silently
    irreversible while reporting success — the same shape of lie the leaf check
    exists to catch.
    """
    Entry = apps.get_model("coach", "ChangelogEntry")
    Entry.all_objects.filter(title=BROKEN_TITLE, kind="NEW").update(kind="ADDED")


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
    dependencies = [("coach", "0064_changelog_sign_in_meets_the_note")]
    operations = [
        migrations.RunPython(repair, unrepair),
        migrations.RunPython(seed, unseed),
    ]
