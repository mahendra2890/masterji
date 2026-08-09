"""The changelog catches up with the streak badge's empty state.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038
and 0039: newest last, so the row created last leads its day under the model's
("-shipped_on", "-id") ordering.

Written as 0040 off 0039, which was main's leaf when this branch opened. Check
the leaf again immediately before the merge button rather than before the test
run — several sessions branch off the same main and one can land in between,
and two leaves stop main deploying, not just this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 10),
        "CHANGED",
        "The streak badge waits until it has something to say",
        "The header used to carry the words \"no run yet\" before you had a "
        "run — a counter announcing that it had nothing to count, in the "
        "corner of the first screen you ever see, in the same grey as four "
        "other words beside it. It told you nothing you did not already know: "
        "of course there is no run on day one. It is simply not there now. "
        "The badge appears the day it has something to report, and the first "
        "thing it ever says is \"1 day\". A run that broke still shows what "
        "it reached — \"0 · best 6\" — because that one is worth reading.",
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
    dependencies = [("coach", "0039_changelog_the_record_reads_right")]
    operations = [migrations.RunPython(seed, unseed)]
