"""The changelog catches up with him knowing the difference between a day
nobody declared on and a day already finished.

Same shape as 0011, 0012, 0016 and 0020: newest last, so the row created last
leads its day under the model's ("-shipped_on", "-id") ordering.

Written as 0021 off 0020 and renumbered to 0022: a sibling session merged its
own 0021 onto main first, and two 0021s off one parent is the two-leaf graph
`migrate` refuses — which would stop main deploying, not just this branch.
Re-parented rather than merged, safe here because this row has never been
applied anywhere but a throwaway local database.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "FIXED",
        "He knows the difference between an empty day and a finished one",
        "File tonight's proof, get it accepted, then keep talking about more "
        "work you did — and he used to answer \"there's no task declared this "
        "morning, so I have nothing to pin it to\", with the card right beside "
        "the chat reading \"Declared: …\" and a green \"✓ accepted\" under it. "
        "Both of those cannot be true. He now says the true one: today's cycle "
        "is already declared, filed and closed, so he has nothing open to pin "
        "it to — and if that was a second piece of real work, declare another "
        "task under Today and file this against it. Several cycles in one day "
        "was always allowed; the sentence pointing you at it was missing. "
        "Either way the draft he wrote out of the conversation comes back to "
        "you in the chat, because the work behind it happened.",
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
    dependencies = [("coach", "0021_changelog_sign_out_lands_home")]
    operations = [migrations.RunPython(seed, unseed)]
