"""The changelog catches up with the chat composer sizing itself.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025 and 0026: newest last, so the
row created last leads its day under the model's ("-shipped_on", "-id")
ordering.

Third row about this one box on 2026-08-09, and the two under it are the honest
record of the day rather than something to tidy away: four lines, then two on a
short screen, then no fixed number at all. They shipped, so they stay.

Written as 0027 off 0026 and renumbered before the first push, the same way 0025
was: main picked up 0027_changelog_mode_caption_says_one_thing from a sibling
session while this branch was being written, and a second 0027 off 0026 is the
two-leaf graph `migrate` refuses — which stops main deploying, not just this
branch. Renamed and re-parented onto main's leaf rather than merged, safe
because this row had never been applied anywhere but a throwaway worktree
database, and was unapplied there before the rename.

Single leaf at write time (0027_changelog_mode_caption_says_one_thing). Check
again before merging — four sessions have collided on this file now.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "The reply box grows as you type",
        "The box you talk to him in is now the size of what you have written "
        "in it. It sits at one line while it is empty and gets a line taller "
        "every time you need one, so the whole of what you are about to send "
        "is in front of you while you write it — and the conversation above "
        "keeps the room you are not using yet. Earlier today it was a fixed "
        "four lines, which managed to be wrong in both directions at once: an "
        "empty slab above the chat before you had typed anything, and still a "
        "line short of anyone whose answer ran to five. Past ten lines it "
        "scrolls, five on a small screen, and the newest thing Masterji said "
        "stays in view while the box grows under it.",
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
    dependencies = [("coach", "0027_changelog_mode_caption_says_one_thing")]
    operations = [migrations.RunPython(seed, unseed)]
