"""The changelog records the phase after the post, and the gate now in front of it.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044, 0046, 0047, 0048, 0049, 0050, 0051, 0052, 0053,
0055 and 0056: newest last, so the row created last leads its day under the
model's ("-shipped_on", "-id") ordering.

Depends on 0057, the schema half of the same change — the phase has to exist as
a column value before it can be described to builders. Two rows because two
things moved for anyone already at LAUNCH: the phase gained an exit it never
had, and the win button moved past it.

Both files were renumbered one up when PR #111 landed 0056 under this branch
mid-flight — the same thing 0055 records happening to it, and the reason the
leaf check runs again immediately before the merge button rather than only
before the tests. A rebase reporting success proves nothing here: git has no
opinion about migration graphs.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "ADDED",
        "TRACTION: the phase after the post",
        "The ladder used to end at LAUNCH, which meant it ended the evening the "
        "post went out — and everything that decides whether the thing is real "
        "happens after that. There is a fifth phase now. Its bar is one "
        "stranger coming back without being asked, or a payment: who paid, how "
        "much, and what for. Repeat beats reach, so a hundred sign-ups who each "
        "opened it once is a worse week than one person who came back on "
        "Thursday. Nothing you have banked moves and no phase you have already "
        "cleared gets harder — this is somewhere to go next, not a new toll on "
        "the way. It is also where the ladder stops: growth, ads and funding "
        "are past what Masterji coaches, and they stay out.",
    ),
    (
        date(2026, 8, 13),
        "CHANGED",
        "LAUNCH has an exit now, and the win button waits for TRACTION",
        "LAUNCH was the last phase, so it never had a gate — nothing followed "
        "it to unlock. Leaving it now costs three accepted proofs, one rung of "
        "the launch ladder per evening, and at least one of the three has to be "
        "a stranger actually doing something rather than another post going "
        "out. Three posts is three evenings of real work and still nobody "
        "acting, which is the same argument BUILD's bar already makes one phase "
        "down. \"Claim the win\" moves with it: it lights on TRACTION's own "
        "proof now, not on the post. If you are already at LAUNCH, the button "
        "you had yesterday is a phase further up — the work behind you is "
        "untouched, and closing a goal is still never blocked from anywhere.",
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
    dependencies = [("coach", "0057_phase_traction")]
    operations = [migrations.RunPython(seed, unseed)]
