"""The changelog records the panels keeping the keyboard, and the half-restored
evening form saying so.

Same shape as the forty before it: newest last, so the row created last leads
its day under the model's ("-shipped_on", "-id") ordering.

Written as 0066 off 0065 and renumbered to 0068 when PR #135 landed 0066 and
0067 on main mid-flight. The rebase reported success and left two leaves —
`check_migration_leaf` is what caught it, which is the whole reason that command
runs before a push and again before the merge button.

Two frontend fixes in one row because they are one evening's work on the same
screen, and because one migration is cheaper than two in a merge queue where
every branch must be up to date before it merges.

Worth a row at all — the honest question here, since neither fix adds a feature.
The first changes what happens when a builder presses a key, and the second puts
a sentence on the proof form that was not there yesterday. Both are things a
builder can see, and the standing call on this boundary is that including it is
fine.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "FIXED",
        "The panels keep the keyboard, and the evening form owns up about the screenshot",
        "Two small things on the way work actually gets filed. If you move "
        "around this app by keyboard — Tab and Escape rather than a mouse — the "
        "panels that open over the dashboard were only half built for you. A "
        "day from your record, a closed idea, a phase, this list: each one said "
        "it was the only thing on screen, and then Tab walked straight out of "
        "it into the page behind, and closing it left you nowhere in "
        "particular. Now opening one puts you in it, Tab stays inside it while "
        "it is open, and closing it puts you back on the row you opened it "
        "from. Nothing moved and nothing looks different; it just works the way "
        "it always claimed to. Separately: when your evening's proof comes back "
        "after a lost tab, the form now tells you that a screenshot cannot come "
        "back with it. Your words and your link are restored the same as "
        "before — an attachment is the one thing that cannot be kept, and "
        "reading your own paragraph exactly as you left it is a good reason to "
        "assume everything else survived too. If you had one picked, pick it "
        "again before you submit.",
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
    dependencies = [("coach", "0067_changelog_the_link_gets_checked")]
    operations = [migrations.RunPython(seed, unseed)]
