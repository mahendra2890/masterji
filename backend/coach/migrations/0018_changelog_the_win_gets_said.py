"""The changelog catches up with a pass over where builders were dropping out.

Same shape as 0011, 0012 and 0016: newest last, so the row created last leads
its day under the model's ("-shipped_on", "-id") ordering.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "FIXED",
        "मास्टरजी is one word again",
        "The wordmark carried Latin letter-spacing, which Devanagari does not "
        "take: the matras came away from the letters they hang on and the "
        "name rendered as four fragments. It had been doing that on the "
        "sign-in page — the first screen anyone sees.",
    ),
    (
        date(2026, 8, 9),
        "CHANGED",
        "Hinglish is a thing you can find now",
        "It was one button showing the language you already had, which is the "
        "one label that gives nobody a reason to press it. Both languages sit "
        "in the header now with the live one lit — the same fix the coach/"
        "thinking-partner switch got, for the same reason.",
    ),
    (
        date(2026, 8, 9),
        "CHANGED",
        "A broken run no longer erases the run that was",
        "Miss two days and the header said 0, which reads as though none of "
        "it happened, at exactly the moment stopping looks reasonable. It now "
        "says 0 next to your longest run on this idea, and the morning after "
        "a break the Today card says which day one this is.",
    ),
    (
        date(2026, 8, 9),
        "FIXED",
        "The gate says so the moment you've earned it",
        "Banking the last proof looked identical to banking none of them: "
        "same quiet button, nothing said, and a builder could stand there for "
        "days already holding what the next phase costs. The card now says it "
        "outright and hands you the phase. Proofs past the bar stopped being "
        "counted into the numerator, too — nobody needed to read '8/3'.",
    ),
    (
        date(2026, 8, 9),
        "FIXED",
        "A refusal stops being true when it stops being true",
        "'Not yet, 0 of 1' used to stay on the goal card after the proof that "
        "answered it landed — sitting under a full bar, contradicting the "
        "counter directly above it. Each answer is now pinned to the "
        "situation it answered and goes when that does.",
    ),
    (
        date(2026, 8, 9),
        "NEW",
        "The front door is a front door",
        "Visiting masterji.mscsoftwares.in used to bounce you straight to a "
        "sign-in wall: a name, one sentence, and a Google button, with every "
        "reason to want the thing living in a README. There is a real page "
        "there now — what it is, what a day with it looks like, and why the "
        "gate is worth trusting — and it no longer asks for an account before "
        "showing you anything.",
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
    dependencies = [("coach", "0017_merge_four_session_changelogs")]
    operations = [migrations.RunPython(seed, unseed)]
