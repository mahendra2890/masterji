"""The changelog records the evening being shown the standard it grades to.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044, 0046 and 0047: newest last, so the row created
last leads its day under the model's ("-shipped_on", "-id") ordering.

Written as 0048 off 0047, main's leaf when this branch opened. Check the leaf
again immediately before the merge button rather than before the test run:
several sessions branch off the same main, one can land in between, and two
leaves stop main deploying rather than just this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 10),
        "FIXED",
        "The evening grades to the same bar you were shown",
        "Under the proof box is a line saying exactly what tonight has to "
        "contain, and Masterji reads it while you talk — it is why he can say "
        "\"that clears it\" in the afternoon. The reading at the end of the day "
        "was never given it. It knew which phase you were in and what you had "
        "declared, and worked out the standard for itself, which is how an "
        "evening could ask for something the afternoon had already called "
        "enough. It now reads the same words you do, from the same place. It is "
        "a floor and not a checklist: your own words, in any order, scruffy, "
        "still clear it. And where he asked you for something specific this "
        "morning, that is still what tonight is judged against — a day spent on "
        "something else earns its proof for the thing you actually did.",
    ),
    (
        date(2026, 8, 10),
        "FIXED",
        "A day already banked can't be written up again",
        "He drafts tonight's proof out of your conversation, and filing that "
        "draft unedited takes one tap and no second opinion — he decided when "
        "he offered it. Describing Tuesday's conversation again tonight got the "
        "same treatment: written up fresh, in new words, so nothing recognised "
        "it as work already on your record, and it banked toward the phase a "
        "second time. He now has every proof you have banked in front of him, "
        "and will not write one of them up twice — he says which day it repeats "
        "and asks what today had in it. A second conversation, different work "
        "the same day, or the next step on something he has already seen are "
        "not repeats, and he still drafts those.",
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
    dependencies = [("coach", "0047_changelog_the_record_he_can_read")]
    operations = [migrations.RunPython(seed, unseed)]
