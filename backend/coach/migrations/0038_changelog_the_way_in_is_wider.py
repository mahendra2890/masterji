"""The changelog catches up with the way into the product.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036 and 0037:
newest last, so the row created last leads its day under the model's
("-shipped_on", "-id") ordering.

Written as 0037 off 0036, which was main's leaf at the time, and renumbered
here: "Three cuts to the cost of a day" merged as PR #42 while this branch was
open and took that number. This is the collision the rule is about, and it
arrived in the hour between writing the file and committing it. Single leaf
again at 0038. Check it once more immediately before the merge button, not
just before the tests — several sessions branch off the same main, so the next
one can land while this is in review. Two leaves stop main deploying, not just
this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "FIXED",
        "The tour's own step controls can be pressed",
        "The four dots that move you through the guided tour were seven pixels "
        "tall with no padding around them — on the phone most of that deck is "
        "read on, they were the one control in it nobody could hit. A slide "
        "runs two to four screens there, so the dots are the only quick way "
        "back to one you have already passed. The dots look exactly as they "
        "did; the button around each one is now four times the size. The "
        "tour's \"Start yours\" link and the \"Sign in\" link in the landing "
        "header got the same treatment, for the same reason.",
    ),
    (
        date(2026, 8, 9),
        "CHANGED",
        "The sign-in popup says what it takes, and how to leave",
        "Two things were missing from the one screen where somebody hands over "
        "a Google account. It now carries Google's own mark, rather than "
        "asking for the account from a button that only claims to be a Google "
        "button, and it says in a line under it what that grants: Masterji "
        "reads your name and email address, and nothing else. There is also a "
        "close button in the corner now. Leaving was always possible — the "
        "backdrop asks, and Escape asks then closes — but a phone has no "
        "Escape key, so the careful dialog read as a trap to exactly the "
        "people it was being careful for. The × asks the same question "
        "the backdrop does, and a second press leaves.",
    ),
    (
        date(2026, 8, 9),
        "NEW",
        "The landing page shows the app instead of describing it",
        "Everything on the front page was an assertion about a coach nobody "
        "had met — a visitor was asked for a Google account having been shown "
        "no part of the product at all. The screens existed only inside the "
        "tour, behind a click most people never spend. There is now one still "
        "frame of the real dashboard on the way down the page: the goal and "
        "its phases, a day that was declared and accepted, and Masterji "
        "declining a tech-stack question in VALIDATION. Every pixel of it is "
        "the app's own stylesheet rather than a drawing of it, which is the "
        "rule the tour already keeps — a second copy of the product drifts "
        "from it the first time either one moves. Still no proof counts on "
        "that page: those live in gates.py, and a marketing page that quotes "
        "them is a promise nothing keeps the day one of them changes.",
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
    dependencies = [("coach", "0037_changelog_the_day_costs_less")]
    operations = [migrations.RunPython(seed, unseed)]
