"""The changelog catches up with the record's dates and the way back to the tour.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037 and
0038: newest last, so the row created last leads its day under the model's
("-shipped_on", "-id") ordering.

Written as 0039 off 0038, which was main's leaf when this branch opened. Check
the leaf again immediately before the merge button rather than before the test
run — several sessions branch off the same main and one can land in between,
and two leaves stop main deploying, not just this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 10),
        "FIXED",
        "Two sentences were missing a space, and one of them was load-bearing",
        "The tour's note on the thinking partner read \"Think with metrades "
        "assignments for questions\", and the front page said the model only "
        "gets to \"proposean advance\". Both are one missing space, and both "
        "came from the same trap: a line of text that begins on its own line "
        "in the source loses the space in front of it when the site is built, "
        "so neither was visible anywhere except in the shipped page. The tour "
        "one mattered more than a typo — that sentence is the only place "
        "Masterji explains what \"Think with me\" is for.",
    ),
    (
        date(2026, 8, 10),
        "FIXED",
        "The record showed the wrong day",
        "A day in your record was printed as \"08-10\", which reads as 8 "
        "October to anyone who writes the day first — and everyone this is "
        "built for writes the day first. It was 10 August. Opening a day, or "
        "reading one back out of a closed idea, showed the raw "
        "\"2026-08-10\" instead. All three now say what you would say: 10 Aug "
        "in the list, 10 Aug 2026 at the top of a day. The record is the part "
        "of this product that has to be trustworthy on its face, and it was "
        "arguing with itself about what day your work happened on.",
    ),
    (
        date(2026, 8, 10),
        "NEW",
        "The guided tour is reachable from inside Masterji",
        "The four-screen tour of how this works could only be opened from the "
        "sign-in popup, so it vanished the moment you had an account — which "
        "is exactly backwards. A visitor can always press the button again; "
        "the person who actually wants it is three days in, looking at a "
        "control they have never understood. \"How it works\" now sits beside "
        "\"What's new\" in the header, and on the goal-commit screen, and "
        "opens the same tour. Nothing in it is a manual: it is the four "
        "screens, the real refusals, and what the two ways of talking to "
        "Masterji are each for.",
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
    dependencies = [("coach", "0038_changelog_the_way_in_is_wider")]
    operations = [migrations.RunPython(seed, unseed)]
