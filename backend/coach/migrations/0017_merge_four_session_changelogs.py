"""Rejoins the three leaves four parallel sessions left behind.

Same failure 0014 was written for, one size up. Four branches ran at once and
each added its own changelog seed off 0014: the where-things-go entry (0015)
with the guided tour stacked on it (0016), the silent-turn entry (0015), and
the mode-control entry (0015). Every one of them is a valid child of 0014 and
none of them knows about the others, so the merged graph has three leaf nodes
and `migrate` refuses the lot — which means `start.sh`, which means the deploy.

No operations, and deliberately no re-parenting of any leaf to sit behind
another, for the reason 0014 gives: a merge is consistent with whichever order
an environment happened to apply them in, while re-pointing dependencies would
leave any database that had already applied a descendant raising
InconsistentMigrationHistory instead — trading a failure that stops the deploy
for one that needs hand-repair.

Numbered 0017 rather than 0015: the highest node here is 0016, and a merge
that sorts above every leaf it joins is the one you can read the graph from.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("coach", "0015_changelog_mode_discovery"),
        ("coach", "0015_changelog_no_messages_at_times"),
        ("coach", "0016_changelog_guided_tour"),
    ]
    operations = []
