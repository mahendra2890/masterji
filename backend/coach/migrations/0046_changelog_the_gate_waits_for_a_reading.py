"""The changelog records the gate learning to tell an outage from a verdict.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040, 0041, 0043 and 0044: newest last, so the row created last leads its
day under the model's ("-shipped_on", "-id") ordering.

Written as 0046 off 0045, this branch's own schema change, which is off 0044 —
main's leaf when this branch opened. Check the leaf again immediately before the
merge button rather than before the test run: several sessions branch off the
same main, one can land in between, and two leaves stop main deploying rather
than just this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 10),
        "FIXED",
        "A day Masterji couldn't read no longer opens a phase",
        "When the model was unreachable your proof was accepted — which kept "
        "your streak alive, and that half was right. The other half was not: "
        "it also counted toward the phase gate. So on a bad afternoon for the "
        "API, \"think about the problem\", proved by \"I thought about it a "
        "lot\", could unlock VALIDATION. The phase whose entire job is to stop "
        "you hiding in planning opened for exactly that. Those were two "
        "decisions riding on one word and they have been split. An evening he "
        "could not read is now filed as not read yet: the day still counts, "
        "it is on your record and in your streak, and nothing about it is held "
        "against you. What it does not do is bank a proof toward the next "
        "phase. Your words stay in the box, and sending them again once he is "
        "answering gets them a real reading — which is all that was ever "
        "missing.",
    ),
    (
        date(2026, 8, 10),
        "FIXED",
        "A stale sign-in no longer locks you out of your own account",
        "If the cookie in your browser had gone bad — expired, mangled, or "
        "left over from another app on localhost — the app answered with an "
        "error it could not read back, decided the server must still be "
        "starting up, and sat on \"The server is waking up.\" retrying every "
        "three seconds. Forever, on a screen with no way out, when the only "
        "thing wrong was a cookie. It now says the session ended, throws the "
        "dead cookie away, and puts you back on the landing page with the "
        "sign-in button where it has always been.",
    ),
    (
        date(2026, 8, 10),
        "CHANGED",
        "Every phase gets its own three questions to open with",
        "The chat has always offered a few things to say when you have not "
        "said anything yet, and they are written per phase — VALIDATION's are "
        "the ones about talking to a stranger without teeing them up to say "
        "yes. Only IDEA's could ever be seen: the test was whether the whole "
        "log was empty, and by the time you earn a phase it never is. The "
        "question is now whether you have said anything in the phase you are "
        "in, so arriving somewhere new brings its own three with it.",
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
    dependencies = [("coach", "0045_alter_checkin_proof_status")]
    operations = [migrations.RunPython(seed, unseed)]
