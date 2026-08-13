"""The changelog records the gate counting people at VALIDATION and kinds of
evidence at BUILD.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043, 0044, 0046, 0047, 0048, 0049, 0050, 0051, 0052 and
0053: newest last, so the row created last leads its day under the model's
("-shipped_on", "-id") ordering.

Depends on 0054, the schema half of the same change — the counting cannot be
described to builders before the columns it counts exist. Both files were
renumbered one up when PR #107 landed 0053 under this branch mid-flight, which
is what a backlog of parallel sessions does to a single-file counter: every PR
here ships a changelog row, so every merge moves the leaf and whoever is second
renumbers. The leaf check has to run immediately before the merge button, not
only before the tests.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "CHANGED",
        "Three conversations means three people",
        "VALIDATION asks for three real conversations, and until now the server "
        "counted evenings rather than people — so three nights of notes about "
        "the same willing friend cleared the phase whose entire purpose is "
        "finding out whether anyone ELSE has the problem. The screenshot on the "
        "landing page has always said the person already counted cannot be "
        "counted again; now the database is what keeps that promise instead of a "
        "sentence in Masterji's instructions. Each accepted conversation is "
        "filed under who it was with, and the gate counts the distinct names. "
        "Nothing you have already banked moves: a proof filed before tonight "
        "counts exactly as it did, and a proof Masterji could not put a name to "
        "counts as its own person. Talking to the same person twice is still "
        "real work, still a proof, still a day on your streak — it just isn't a "
        "second opinion.",
    ),
    (
        date(2026, 8, 13),
        "CHANGED",
        "One of BUILD's two proofs has to be somebody using the thing",
        "BUILD takes either kind of evidence on any given night — a link to "
        "something running, or proof that a real user touched it — and that was "
        "true of the phase exit too, so two evenings of deploys could open "
        "LAUNCH with nobody having opened the thing. Shipping at a "
        "people-shaped problem is the most comfortable way to avoid the people, "
        "which is the one move BUILD exists to stop. So the exit now costs two "
        "proofs AND at least one of them being a real user doing something with "
        "it: what they did, when, and whether anyone asked them to. Tonight's "
        "bar has not changed — a link that loads is still a proof and still a "
        "day. The gate card says which of the two is still missing rather than "
        "waiting for you to press the button and find out.",
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
    dependencies = [("coach", "0054_checkin_subject_and_proof_parts")]
    operations = [migrations.RunPython(seed, unseed)]
