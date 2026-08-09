"""The changelog catches up with three cuts to the daily loop.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026 and 0035: newest last,
so the row created last leads its day under the model's ("-shipped_on", "-id")
ordering.

Written as 0036 against a single leaf (0035) and renumbered to 0037 an hour
later, because main merged "The chat is where the proof comes from" off that
same parent while this branch was open and its seed took 0036. That is the
normal weather here, not bad luck.

Check again immediately before the merge button rather than before the tests.
Two leaves stop main deploying, not just this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "CHANGED",
        "The morning ends when the morning ends",
        "Declaring a task used to unfold the whole evening under it — what "
        "tonight has to contain, the proof box, the link field, the "
        "screenshot, and Submit proof — four fifths of the card, for work "
        "nobody can do for another ten hours. Masterji asks for about two "
        "minutes a day and the screen after those two minutes looked like "
        "homework. Now the morning closes: he takes the task, says what he "
        "makes of it, and tells you nothing is owed until tonight. The "
        "evening is one press away, and it opens by itself once there is an "
        "evening to open — a push-back to answer, a try already made, notes "
        "he has started writing, or simply five o'clock.",
    ),
    (
        date(2026, 8, 9),
        "NEW",
        "Three things to say, when the chat is empty",
        "A new chat was one message from him, a blank box and \"Talk it "
        "through…\", which is a thin invitation to the habit the rest of the "
        "day rests on: the draft that makes filing your proof one tap is "
        "written out of this conversation, so a builder who never talks here "
        "writes every evening from nothing. There are now three questions "
        "under his first message — real ones, and different in each phase. "
        "Tapping one fills the box for you to edit. They disappear the moment "
        "you have said anything of your own, and they move the gate by "
        "nothing.",
    ),
    (
        date(2026, 8, 9),
        "FIXED",
        "Signing out asks first",
        "\"sign out\" was a sixteen-pixel word in the corner of the header a "
        "thumb rests in, a hair away from \"What's new\", and it fired on the "
        "first press. Missing cost you the session and a full round trip "
        "through Google. It is a proper target now, it asks once before it "
        "goes, and the question drops the moment you look elsewhere. It also "
        "stopped being the only underlined thing on the screen — an odd "
        "honour for the door.",
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
    dependencies = [("coach", "0036_changelog_the_talking_becomes_the_proof")]
    operations = [migrations.RunPython(seed, unseed)]
