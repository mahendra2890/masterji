"""The reply box stops sending when a phone asks it for a new line.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0027, 0030 and 0031:
newest last, so the row created last leads its day under the model's
("-shipped_on", "-id") ordering.

Single leaf at write time (0031). Check again immediately before merging — on
2026-08-09 a branch had to renumber twice in half an hour because sibling
sessions kept landing seeds off the same parent.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "FIXED",
        "On a phone, the return key makes a line instead of sending",
        "Enter sent your reply and Shift+Enter started a new line — a bargain "
        "that needs a Shift key to keep. A phone doesn't have one, so the ⏎ on "
        "the keyboard, the one key there for starting a paragraph, sent the "
        "message instead: half a thought, gone, and no way to type the second "
        "half. On phones and tablets the return key now does what its icon "
        "says and Send is what sends. On a desktop nothing changes — Enter "
        "still sends, Shift+Enter still breaks the line.",
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
    dependencies = [("coach", "0031_changelog_mode_bar_is_a_control_again")]
    operations = [migrations.RunPython(seed, unseed)]
