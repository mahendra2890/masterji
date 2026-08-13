"""The changelog records the gate saying why three proofs can read as one.

Same shape as every changelog migration before it (0049 through 0055): newest
last, so the row created last leads its day under the model's ("-shipped_on",
"-id") ordering.

Depends on 0055, which shipped the counting this one explains. That gap — one
merge between a gate changing how it counts and the screen admitting it — is
the whole of what this row is for.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "CHANGED",
        "Three proofs, one person: the gate now says so",
        "Since VALIDATION started counting people rather than evenings, three "
        "accepted nights of notes about the same person have read as 1/3 — "
        "true, and impossible to make sense of from the outside. It looked like "
        "the gate had quietly lost two nights of work. It hadn't, and it never "
        "will: every proof you banked is still banked, still on the record, "
        "still a day on your streak. What was missing was the sentence saying "
        "which number you were looking at. The gate card now reads them both — "
        "how many proofs are in, how many different people they were with — and "
        "the refusal says the same thing without waiting for you to press the "
        "button and find out. Masterji is told both numbers too, so if you tell "
        "him you filed three he will agree with you instead of arguing with his "
        "own record. If two of your conversations came back under the "
        "same name and they were genuinely two people, write the second one "
        "down more precisely tonight and the count will agree with you.",
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
    dependencies = [("coach", "0055_changelog_people_and_kinds")]
    operations = [migrations.RunPython(seed, unseed)]
