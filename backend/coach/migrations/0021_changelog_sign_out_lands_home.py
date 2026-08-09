"""Signing out now lands on the landing page instead of the sign-in wall.

Same shape as every changelog seed before it: newest last, so the row created
last leads its day under the model's ("-shipped_on", "-id") ordering.

Written as 0020 off 0019, then renumbered: a parallel session landed
0020_changelog_tour_shows_the_win on main first, and two 0020s off the same
parent is the two-leaf graph `migrate` refuses — the failure 0014, 0017 and
0019 were each written to repair. Re-parenting behind that leaf rather than
adding a fourth merge migration, which is the opposite of what 0019 warns
about and safe for the reason 0019 gives: its warning is about moving a
migration some environment has already applied. This one has never been
applied anywhere, so nothing can raise InconsistentMigrationHistory over it,
and the graph stays linear.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "Signing out puts you at the front door",
        "Sign out and you were dropped on the sign-in page — a wordmark and a "
        "Google button — which answers 'I'm done' by asking for the account "
        "you just put down. You land on the home page now, the one screen "
        "that says what this is, with Sign in still in the corner for "
        "whenever you want back in.",
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
    dependencies = [("coach", "0020_changelog_tour_shows_the_win")]
    operations = [migrations.RunPython(seed, unseed)]
