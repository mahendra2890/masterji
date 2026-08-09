"""The changelog records the changelog getting cheaper to carry.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041 and 0043: newest last, so the row created last leads its day
under the model's ("-shipped_on", "-id") ordering.

Written as 0044 off 0043, main's leaf when this branch opened. Check the leaf
again immediately before the merge button rather than before the test run —
several sessions branch off the same main and one can land in between, and two
leaves stop main deploying, not just this branch. This branch's own history is
the reason to bother: the pair before it was renumbered twice.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 10),
        "CHANGED",
        "Every page got lighter, and this list is why",
        "Masterji keeps this record because he demands one from you — and it "
        "has been growing since the first build, which is the point of it. But "
        "every screen in the product was downloading the whole thing on load, "
        "all seventy-seven entries and 42KB of them, just to work out whether "
        "to put an orange dot next to \"What's new\". That was being paid by "
        "everyone, on the landing page, before they had clicked anything, on "
        "whatever connection they happened to be on. A page now fetches the "
        "newest six — about a tenth of that — and opening this popup is what "
        "asks for the rest. If the older ones are still on their way, it says "
        "so at the bottom rather than making you wait for the newest one.",
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
    dependencies = [("coach", "0043_changelog_the_app_stays_light")]
    operations = [migrations.RunPython(seed, unseed)]
