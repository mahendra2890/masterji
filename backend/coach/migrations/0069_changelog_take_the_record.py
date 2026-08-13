"""The changelog records the record leaving the app, whole.

Same shape as every changelog migration before it: newest last, so the row
created last leads its day under the model's ("-shipped_on", "-id") ordering.

One row for two issues (#85 and #88), because from the builder's side they are
one change: the record can be taken out of the app, and it is all of it. Shipping
the file without lifting the cap would have meant handing someone a document that
called itself the whole story and quietly began three months in.

No schema half — nothing new is stored. The export is a rendering of rows that
were already there.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "NEW",
        "Take your record with you",
        "Every goal now has a download: one file with the whole of it — each "
        "day's declared task, the proof you filed, what Masterji made of it, the "
        "tries he pushed back, the dates the phases opened, and how the idea "
        "ended. It is the same record the app has always shown you, in something "
        "you can attach to an E-Cell application or open in front of somebody at "
        "an interview. The tries that were refused are in there on purpose: a "
        "record that shows only the proofs that landed is a brochure, and the "
        "refusals are what make the rest of it worth reading. Nothing about it "
        "is self-reported — every number in the file was counted by the server "
        "from proofs you had to earn. Screenshots are named but not included, "
        "because the app serves those over links that expire and a file full of "
        "dead links is worse than one that says a screenshot was filed. "
        "Alongside it, the record on your dashboard stopped forgetting: it kept "
        "the most recent ninety days and \"Show all\" offered you exactly those "
        "ninety, so a goal that ran longer than three months lost its "
        "first weeks with nothing to say they had been there. It now says how "
        "many days exist and goes and gets the rest when you ask for them.",
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
    dependencies = [("coach", "0068_changelog_the_panels_hold_the_keyboard")]
    operations = [migrations.RunPython(seed, unseed)]
