"""The changelog records three playbooks filling the corpus's thin shelves.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044, 0046, 0047, 0048, 0049 and 0050: newest last, so
the row created last leads its day under the model's ("-shipped_on", "-id")
ordering.

One row for three files on purpose. They ship together and they are one change
to the same thing — what the coach has read — even though a builder only ever
meets the one wired to the phase they are standing in.

Written as 0050 off 0049, and renumbered to 0051 when the finish-line fix landed
on main under this branch mid-flight (PR #104) and took that number off 0049 as
well. The rename is the visible half; `dependencies` repointing at what actually
landed is the half that matters, because two migrations sharing a parent is two
leaves however they are named, and two leaves stop main deploying rather than
just this branch. The rebase that pulled #104 in reported success either way —
git has no opinion about migration graphs. Both files seed a changelog row on
2026-08-13 and neither touches schema, so what the renumber decides is only
which of the two leads that day: applied last means the higher id, and under
("-shipped_on", "-id") this row sits above the finish-line one. That is the
right way round — three playbooks is the larger change of the two.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "METHOD",
        "Three playbooks for the moments the corpus went quiet",
        "The coach's whole knowledge base is a folder of markdown you can read "
        "in ten minutes, and until now it had nothing to say at three of the "
        "hardest moments. VALIDATION had the heaviest gate in the product — "
        "three conversations — and one playbook, which told you what to say "
        "once you were in the room and nothing about getting into it. Getting "
        "the Conversation is that missing half, distilled from Giff "
        "Constable's \"Talking to Humans\": ask for advice rather than "
        "pitching, what the first message has in it, why five sent to get one "
        "reply is the rate and not a verdict, and the intro ask that ends "
        "every conversation. LAUNCH said a ₹99 payment tells the truth and "
        "taught no way to get one. The First Rupee, from Rob Walling and "
        "Patrick McKenzie's pricing writing, prices against the workaround "
        "already in your notes, refuses \"would you pay?\" the same way the "
        "conversations playbook refuses it, and treats \"too expensive\" as "
        "the start of the conversation. And IDEA — where the first question "
        "anybody asks is whether the idea is any good — was answered out of "
        "the model's general knowledge rather than anything credited. "
        "Choosing the One Idea, from Paul Graham on where ideas come from and "
        "Dalton Caldwell on tarpits, is noticed-beats-invented, the campus "
        "tarpits by name, schlep blindness, and the tiebreak that decides it: "
        "whose room can you actually walk into this week. None of this moves "
        "a gate. The bars are exactly where they were.",
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
    dependencies = [("coach", "0050_changelog_the_finish_line_counts_launch")]
    operations = [migrations.RunPython(seed, unseed)]
