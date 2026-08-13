"""The changelog records typed work surviving a tab the phone discarded.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044, 0046, 0047, 0048, 0049, 0050, 0051, 0052, 0053, 0055,
0056 and 0058: newest last, so the row created last leads its day under the model's
("-shipped_on", "-id") ordering.

FIXED rather than CHANGED, and the same kind 0052 took: nothing new is on the
screen, and what the builder notices is a failure they had already learned to
work around.

Renumbered twice on the way in — 0056 → 0057 when #109's row reached main, then
0057 → 0059 when TRACTION's schema and changelog rows did. Both are the collision
0052's note predicts, and both were caught by checking the leaf again rather than
by the rebase, which reported success each time. Per 0052's note, every PR in this backlog
ships a changelog row, so the leaf moves on every merge and whoever is second
renumbers: check again immediately before the merge button, not only before the
tests, because a clean rebase will happily leave two leaves off the same parent.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "FIXED",
        "A notification mid-sentence no longer costs you the paragraph",
        "A phone reclaims a background tab whenever it wants the memory, and "
        "an evening's proof is a paragraph of real thinking typed on a phone "
        "keyboard. Until now, anything not yet submitted died with the tab: a "
        "WhatsApp notification halfway through writing up the conversation you "
        "just had, and the answer was to type it again at ten at night — which "
        "is how a day you actually worked silently becomes a missed one. Three "
        "boxes now keep what you typed and put it back when you return: this "
        "morning's task, tonight's proof with its link, and whatever you were "
        "part-way through saying to Masterji. Each one is held against the "
        "thing it belongs to, so tonight's box never opens holding yesterday's "
        "words: the morning's draft is filed under the day, the proof under the "
        "task it is evidence for, and anything older than about eighteen hours "
        "is dropped rather than resurfaced. It stays on your own phone, never "
        "reaches the server, and nothing about it counts for anything — a draft "
        "is not a proof, and only what you submit is ever read or banked. An "
        "attachment is the one thing that cannot be kept; if you had picked a "
        "screenshot, pick it again before you submit.",
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
    dependencies = [("coach", "0058_changelog_traction")]
    operations = [migrations.RunPython(seed, unseed)]
