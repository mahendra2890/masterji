"""Refuse a migration graph that has grown a second leaf in any one app.

The characteristic failure of running sessions in parallel, and the one that
stopped `main` deploying three times: two sessions each add a migration, each
numbered correctly against the `main` it branched from, and neither can see the
other. Together they are two leaf nodes and `migrate` refuses to guess.

The rule that fixed it — verify a single leaf before pushing and again
immediately before merging — was written into persistent memory, where it holds
for exactly as long as every future session remembers to run it. This is that
same rule as a command, so the ritual and the automated check are the same
thing rather than two things that can disagree.

Reads the graph off disk. `MigrationLoader(None)` takes no connection, so this
needs no database and says nothing about what has been applied anywhere — only
about the files in the tree, which is the whole of the question.
"""

from collections import defaultdict
from collections.abc import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db.migrations.loader import MigrationLoader


def multi_leaf_apps(leaf_nodes: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    """Apps holding more than one leaf, each with every name that collided.

    Checks every app in the graph rather than `coach` alone: `migrate` refuses
    on a second leaf wherever it is, and `accounts` takes migrations too.
    """
    by_app: dict[str, list[str]] = defaultdict(list)
    for app, name in leaf_nodes:
        by_app[app].append(name)
    return {app: sorted(names) for app, names in by_app.items() if len(names) > 1}


class Command(BaseCommand):
    help = "Fail if any app's migration graph has more than one leaf node."

    def handle(self, *args, **options):
        graph = MigrationLoader(None, ignore_no_migrations=True).graph
        leaves = list(graph.leaf_nodes())
        found = multi_leaf_apps(leaves)
        if found:
            # Both names, because the fix is to renumber one onto the other and
            # a message naming only the app leaves you diffing to find which two
            # collided. Raised rather than printed: CommandError exits non-zero,
            # and a warning in a log nobody opens is the state this replaces.
            detail = "; ".join(
                f"{app}: {' and '.join(names)}" for app, names in sorted(found.items())
            )
            raise CommandError(
                f"More than one migration leaf — {detail}. Renumber yours onto "
                "main's leaf and repoint its `dependencies`. A rebase reporting "
                "success proves nothing here: git has no opinion about migration "
                "graphs."
            )
        for app, name in sorted(leaves):
            self.stdout.write(f"{app}: {name}")
        self.stdout.write(self.style.SUCCESS("One leaf per app."))
