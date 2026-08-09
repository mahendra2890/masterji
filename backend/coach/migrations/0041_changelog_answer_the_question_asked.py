"""The changelog records that Masterji stopped refusing questions nobody asked.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026 and 0035-0040: newest
last, so the row created last leads its day under the model's ("-shipped_on",
"-id") ordering.

Written as 0040 off 0039 and renumbered to 0041 within the hour, because main
merged its own 0040 off that same parent while this branch was under review.
Check the leaf again immediately before the merge button rather than before the
test run — several sessions branch off the same main and one can land in
between, and two leaves stop main deploying, not just this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 10),
        "FIXED",
        "Masterji was answering questions you hadn't asked",
        "Tap \"Who exactly has this problem?\" in IDEA — the first thing this "
        "app suggests you say to him — and he replied \"you're asking the "
        "right thing, but not the right week for stack or features.\" Nobody "
        "had mentioned a stack or a feature. Asked about it, he admitted as "
        "much: \"You didn't. I'm correcting the drift before it starts.\" The "
        "rule that holds tech talk back until BUILD was written as something "
        "to do rather than something to do when you bring it up, so it fired "
        "at builders who never went near the subject — on the phase's own "
        "central question, usually in the first exchange. It now only answers "
        "the question you actually asked, and a question that IS this week's "
        "work gets an answer instead of a warning.",
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
    dependencies = [("coach", "0040_changelog_the_zero_badge_goes_quiet")]
    operations = [migrations.RunPython(seed, unseed)]
