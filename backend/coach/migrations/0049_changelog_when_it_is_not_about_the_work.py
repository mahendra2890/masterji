"""The changelog records the coach answering the person instead of the task.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044, 0046, 0047 and 0048: newest last, so the row
created last leads its day under the model's ("-shipped_on", "-id") ordering.

Written as 0048 off 0047, and renumbered to 0049 when 0048 landed on main under
this branch mid-flight (PR #56, the judge's bar). The rename is the visible half
and the smaller one: `dependencies` had to be repointed at what actually landed,
because two migrations sharing a parent is two leaves however they are named,
and two leaves stop main deploying rather than just this branch. That was worth
noticing here — the collision was known when this file was written, and the
rebase that pulled the other one in reported success, because git has no opinion
about migration graphs. Check the leaf immediately before the merge button as
well, not only before the test run.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 10),
        "CHANGED",
        "Some nights aren't about the work",
        "Masterji's answer to a builder who is stuck has always been the same: "
        "name what you're avoiding, and here's the smallest real thing to do "
        "next. That is the right answer to being stuck on the work. It was also "
        "the only answer he had, which made it his answer to \"my parents want "
        "me to stop wasting time on this\" and to \"I can't keep doing this\" — "
        "and being handed a task is not what either of those needs. He now "
        "reads a message like that for what it is and answers you, not the "
        "task: no assignment that turn, no declaration demanded, nothing about "
        "avoidance. He'll tell you the true things he has — missing days "
        "deletes nothing you already banked, closing a goal is free and always "
        "was, and a goal you're keeping out of guilt is worth less than the one "
        "you'd choose today. He stays himself while he does it: no counsellor "
        "voice, no diagnosis, no list of techniques. And if it's bigger than a "
        "hard week he'll say plainly, once, that a coaching app isn't what you "
        "need and a person you trust is. None of this touches the gate — "
        "nothing gets banked because a night was hard, and if you mention real "
        "work in the same breath he still writes it down for you.",
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
    dependencies = [("coach", "0048_changelog_the_judge_can_see_the_bar")]
    operations = [migrations.RunPython(seed, unseed)]
