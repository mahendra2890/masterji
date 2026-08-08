"""Rejoins the two 0012s into one leaf.

Two branches each added a changelog seed off 0011 — the day-record entry and
the thinking-partner entries — and landed within an hour of each other. Django
refuses to migrate a graph with two leaf nodes, so `migrate` (and therefore
`start.sh`, and therefore the deploy) fails until something names both of them
as its parents. That is all this file is.

No operations, and deliberately no re-parenting of either 0012 to sit behind
the other: whichever one an environment happened to apply first, a merge is
consistent with it. Re-pointing dependencies would leave any database that had
already applied the descendant raising InconsistentMigrationHistory instead —
trading a failure that stops the deploy for one that needs hand-repair.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("coach", "0012_changelog_day_record"),
        ("coach", "0013_checkin_proof_offer"),
    ]
    operations = []
