"""The changelog records the commit screen pricing what it asks for, and the
coach answering idea-doubt instead of defending the goal.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044, 0046, 0047, 0048, 0049, 0050, 0051 and 0052:
newest last, so the row created last leads its day under the model's
("-shipped_on", "-id") ordering.

One row for two changes, because a builder meets them as one thing — whether
this idea is worth their weeks, asked before commit and again after it. Split
into two rows the second would read as a separate feature.

Numbered 0053 off 0052 as it landed. Per 0052's own note, every PR in this
backlog ships a changelog row, so the leaf moves on every merge and whoever is
second renumbers: check again immediately before the merge button, not only
before the tests, because a clean rebase will happily leave two leaves off the
same parent.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "CHANGED",
        "Committing is picking what you'll test first",
        "Two changes for one moment: deciding whether an idea deserves your "
        "weeks. The commit screen used to say \"pick the one that matters\" and "
        "price the daily cost — about two minutes a day — without ever saying "
        "what you were agreeing to finish, which is how a first goal starts "
        "feeling like a promise to see it through. It now says what was always "
        "true: you are picking the problem you test first, not the idea you "
        "finish; the first thing asked of you is one evening at your desk; and "
        "an idea that dies in front of real people reads as tested on your "
        "record rather than failed. Most first ideas should. Second, when you "
        "ask Masterji whether this is even the right idea — the doubt that "
        "arrives after committing, not before — he no longer puts the problem "
        "statement back in front of you and asks what you are doing tonight. He "
        "answers it: the proof in front of you is the readiness test and "
        "finishing it is the short route to knowing, closing this goal is free "
        "and the record survives it, and a goal kept out of guilt is worth less "
        "than the one you would choose now. Then he names the two doors and "
        "leaves the choice with you. None of this touches the gate — wavering "
        "banks nothing, and nothing you say in chat ever moves a phase.",
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
    dependencies = [("coach", "0052_changelog_the_night_owl_rule")]
    operations = [migrations.RunPython(seed, unseed)]
