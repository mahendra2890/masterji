"""The changelog catches up with the sign-in page going away, and the tour
losing five slides.

Same shape as 0011, 0012, 0016, 0020 and 0027: newest last, so the row created
last leads its day under the model's ("-shipped_on", "-id") ordering.

Written as 0028 and renumbered to 0029: a sibling session merged its own 0028
(the reply box growing as you type) onto main off the same 0027 parent first,
and two 0028s off one parent is the two-leaf graph `migrate` refuses — which
stops main deploying, not just this branch. Re-parented rather than merged,
safe because this row had only ever been applied to a throwaway local database,
and was unapplied before the rename.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "Signing in happens where you are, and the tour got shorter",
        "Two changes to everything before the app. The sign-in page is gone: "
        "pressing \"Start free with Google\" used to load a page holding a "
        "wordmark and one button, which answered a decision by asking for it "
        "again. The same press now opens sign-in over the page you were "
        "reading, blurred behind it — the argument that got you that far stays "
        "on screen while you make the account. Clicking away doesn't lose it "
        "either: it asks whether you meant to go back, and staying is one "
        "button. The guided tour is four slides instead of nine. It had grown "
        "into a manual for a product nobody had signed up for yet — the phase "
        "diagram and the four-line day the home page already spells out, how "
        "to retire a goal nobody has made, the running proof notes the screen "
        "announces by itself. What's left is the three things worth knowing "
        "before you commit: your first two minutes, which of the two boxes "
        "counts, and what the gate does when you ask it early.",
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
    dependencies = [("coach", "0028_changelog_the_box_grows_as_you_type")]
    operations = [migrations.RunPython(seed, unseed)]
