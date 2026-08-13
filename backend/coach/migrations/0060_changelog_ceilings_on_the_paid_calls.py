"""The changelog records ceilings on the three endpoints that cost money.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044, 0046, 0047, 0048, 0049, 0050, 0051, 0052, 0053, 0055,
0056, 0058 and 0059: newest last, so the row created last leads its day under the model's
("-shipped_on", "-id") ordering.

Written even though no honest builder will meet one of these — thirty turns an
hour and twenty filings a day are multiples of real use — because the thing
worth saying is not the number. It is that a shared budget exists, that it is
what every verdict comes out of, and that nothing here touches the gate.

Renumbered twice on the way in — 0056 → 0057 when #109's row reached main, then
0057 → 0060 when TRACTION's two rows and the drafts row went in ahead of it. Both
are the collision 0052's note predicts, and neither was caught by the rebase,
which reported success each time. The leaf check is what caught them. Per 0052's note, every PR in this backlog
ships a changelog row, so the leaf moves on every merge and whoever is second
renumbers: check again immediately before the merge button, not only before the
tests, because a clean rebase will happily leave two leaves off the same parent.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "CHANGED",
        "Ceilings on the three things that cost money to answer",
        "Reading your task in the morning, judging your proof at night and "
        "answering you in chat are all paid calls to a model, and until now "
        "nothing capped how many of them one account could ask for. That "
        "budget is shared: it is what every builder's verdict comes out of, so "
        "one script pointed at it is everybody else's evening. There are now "
        "ceilings — thirty chat turns an hour, twenty filings a day, forty "
        "readings of the morning's task — set at multiples of real use, so an "
        "honest week never meets one. There are also limits on length: a "
        "proof can run to several paragraphs because conversation notes do, "
        "while a declared task is one sentence and is held to it. If you ever "
        "do hit a ceiling you are told so in plain words and nothing is lost — "
        "declaring stays free and unlimited, and a reading of your task that "
        "gets refused leaves the day exactly as a model outage does: declared, "
        "yours, and provable tonight. None of this is a coaching limit and none "
        "of it can touch the gate: a refused request is not a refused proof, "
        "and what a phase costs is unchanged.",
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
    dependencies = [("coach", "0059_changelog_drafts_survive_the_tab")]
    operations = [migrations.RunPython(seed, unseed)]
