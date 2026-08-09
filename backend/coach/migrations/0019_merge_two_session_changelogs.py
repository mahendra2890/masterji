"""Rejoins the two leaves this pair of parallel sessions left behind.

The same failure 0014 and 0017 were written for, at its smallest size. Two
branches ran at once off 0017 and each added its own changelog seed: the tour
rewrite's entry and this session's drop-off pass. Both are valid children of
0017 and neither knows about the other, so the merged graph has two leaf nodes
and `migrate` refuses the lot — which means `start.sh`, which means the deploy.

No operations, and deliberately no re-parenting of either leaf behind the
other, for the reason 0014 gives: a merge is consistent with whichever order
an environment happened to apply them in, while re-pointing dependencies would
leave any database that had already applied a descendant raising
InconsistentMigrationHistory instead — trading a failure that stops the deploy
for one that needs hand-repair.

Numbered 0019 rather than 0018: a merge that sorts above every leaf it joins
is the one you can read the graph from.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("coach", "0018_changelog_the_win_gets_said"),
        ("coach", "0018_changelog_tour_starts_at_the_start"),
    ]
    operations = []
