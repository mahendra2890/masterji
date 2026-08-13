"""The changelog records the win button waiting for a LAUNCH proof.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044, 0046, 0047, 0048 and 0049: newest last, so the row
created last leads its day under the model's ("-shipped_on", "-id") ordering.

Written as 0050 off 0049, which was main's leaf when this branch opened. 0049's
own docstring is the reason to check again at the merge button rather than trust
this line: a rebase reports success without having an opinion about the
migration graph, and two migrations sharing a parent is two leaves whatever they
are named.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "FIXED",
        "The win button waits for the post to go out",
        "\"Claim the win\" used to appear the moment you reached LAUNCH. It was "
        "counting every proof you had ever banked, and you cannot reach LAUNCH "
        "without banking six of them — so the most prominent button on the "
        "screen offered you the exit on the first morning of the phase, before "
        "you had posted anything, which is the one piece of work LAUNCH is for. "
        "It now waits for one accepted proof filed in LAUNCH itself: the link "
        "to your post, what a stranger actually did, or a real rejection with "
        "the reason they gave. Nothing about closing a goal changed. The quiet "
        "link is where it always was, \"I achieved it\" is still there for a "
        "goal you finished from anywhere, and the record still counts every "
        "proof you earned in any phase when it decides whether that reads as "
        "achieved. What changed is only which moment the app calls the finish "
        "line.",
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
    dependencies = [("coach", "0049_changelog_when_it_is_not_about_the_work")]
    operations = [migrations.RunPython(seed, unseed)]
