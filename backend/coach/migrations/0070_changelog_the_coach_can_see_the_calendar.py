"""The changelog records that the coach can see the calendar, and clears a debt.

Same shape as every changelog migration since 0011: newest last, so the row
created last leads its day under the model's ("-shipped_on", "-id") ordering.

Two rows, and the first of them is older than this branch. PR 126 shipped two
things a builder can see — the terminal-phase refusal that named the wrong
phase, and a coach being told the gate was met while the server refused it —
and shipped no row for either. It is the same PR that asked where the changelog
boundary sits and was answered "including is fine"; the answer arrived and the
row never did (#133). Carried here rather than in a PR of its own because a
changelog row alone would cost a whole rebase-and-CI cycle in a merge queue that
now requires branches to be up to date, and because this branch is already
editing the state block that PR fixed.

CHANGED, not NEW, for the calendar row: the coach could always be talked to
after a week away. What changed is that he now knows the week happened.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "FIXED",
        "Two sentences that described your gate wrongly",
        "Two places where what Masterji said about your progress did not match "
        "what the server was doing. Pressing Advance at the last phase said "
        '"you\'re at LAUNCH" to builders who were standing at TRACTION — and '
        "that sentence is kept in your transcript, so the wrong one stayed "
        "there. And in a phase that asks for a KIND of evidence as well as a "
        "count — two build evenings, one of them a real user touching it — the "
        "coach was told the gate was met as soon as the count was, while the "
        "server went on refusing it. He was agreeing with you about a door that "
        "would not open. Both now read the same thing the gate reads. Nothing "
        "about what a phase costs changed, and nothing you banked moved.",
    ),
    (
        date(2026, 8, 13),
        "CHANGED",
        "The coach knows how long it has been, and so do you",
        "Masterji could see your phase, your count and your streak, and not one "
        "date. So a fortnight in VALIDATION was described to him exactly like a "
        "second day, and a builder coming back after a silent week was "
        "described exactly like one who was here last night — which is why he "
        "sometimes greeted a comeback as though nothing had happened. He now "
        "gets two facts: how long the current phase has been open, and how long "
        "since your last complete day. The first is about the work and he may "
        "use it like anything else — three weeks and one conversation is worth "
        "saying out loud. It is also on your goal card now, under the ladder: "
        "\"12 days in VALIDATION\", from the day after a phase opens, and it is "
        "the same number he is holding, measured once on the server so the two "
        "can never disagree. What it is not is a deadline. This product does "
        "not set any, a phase taking a long time is not late, and that line "
        "will never change colour or start looking urgent at you, because "
        "there is nothing for it to be late for. The second is "
        "there for one reason only: so he does not talk past a week you were "
        "away. He will not open with it, ask where you were, or add up what was "
        "missed. Nothing was lost while you were gone — every banked proof, "
        "your record and your best run are where you left them, and only the "
        "current streak starts again. None of this is read by the gate: a "
        "phase costs exactly what it cost before, and a quiet fortnight banks "
        "and un-banks nothing.",
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
    dependencies = [("coach", "0069_changelog_take_the_record")]
    operations = [migrations.RunPython(seed, unseed)]
