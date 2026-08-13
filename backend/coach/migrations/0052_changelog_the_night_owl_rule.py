"""The changelog records proofs filed after midnight landing on the evening
that earned them.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044, 0046, 0047, 0048, 0049, 0050 and 0051: newest
last, so the row created last leads its day under the model's ("-shipped_on",
"-id") ordering.

Written as 0050 off 0049, renumbered to 0051 when PR #104 landed 0050 under
this branch mid-flight, and renumbered again to 0052 when PR #106 landed 0051
before this one merged. Twice in one afternoon, which is what a backlog of
parallel sessions does to a single-file counter: every PR here ships a
changelog row, so every merge moves the leaf and whoever is second renumbers.
Both times the rebase reported success and left TWO leaves off the same
parent — git has no opinion about migration graphs, so the leaf check is the
only thing that sees it, and it has to run immediately before the merge button
rather than only before the test run. `dependencies` points at what actually
landed.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "FIXED",
        "The evening ends when you stop working, not at midnight",
        "Work finished at 00:30 is last night's work, and the app used to "
        "disagree. The clock rolled over while you were typing, so the proof "
        "arrived on a day nothing had been declared on: it was refused with "
        "\"No declaration this morning — proof of what, exactly?\", the task "
        "you had been working on all evening was replaced by an empty morning "
        "form, and the streak broke on a day you had actually finished. It hit "
        "exactly the people who work after dinner, which is most of you. Now a "
        "proof filed in the small hours lands on the cycle that is still open "
        "from last night, and the day it completes is the day you declared it "
        "— the dashboard keeps showing that task until you file against it, "
        "and Masterji drafts toward the same one. The window closes on its own "
        "a few hours after midnight: this is for the evening that ran long, "
        "not a way to go back and fix a day you missed. Declaring a new task "
        "after midnight still opens a new day, and last night's stays exactly "
        "where it is.",
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
    dependencies = [("coach", "0051_changelog_three_playbooks")]
    operations = [migrations.RunPython(seed, unseed)]
