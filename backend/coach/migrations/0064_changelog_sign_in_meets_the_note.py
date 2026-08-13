"""The changelog records that sign-in no longer opens onto Render's boot logs.

Same shape as every changelog migration since 0011: newest last, so the row
created last leads its day under the model's ("-shipped_on", "-id") ordering.

FIXED rather than CHANGED. The cold-start note already existed and was already
the intended behaviour; the sign-in click was simply never routed through it,
which is a gap, not a new idea.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "FIXED",
        "Signing in during a cold start says so, instead of showing boot logs",
        "The note that explains the wait when the server has been asleep has "
        "been up since the admin pages got it, but the Sign in button never "
        "reached it. That button is a link straight to Google by way of the "
        "backend, so a click during a cold start left the product entirely and "
        "landed on the host's own startup log — a black screen scrolling "
        "ALLOCATING COMPUTE RESOURCES at somebody whose whole experience of "
        "Masterji so far was deciding to try it. It never said how long it "
        "would take, and it read as a site that had broken. Now the same note "
        "everything else gets stands in front of it: it says the server is "
        "waking, it waits, and it sends you on to Google the moment the "
        "backend answers. The host's log is still one click away for anyone "
        "who would rather watch it.",
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
    dependencies = [("coach", "0063_changelog_the_workshop")]
    operations = [migrations.RunPython(seed, unseed)]
