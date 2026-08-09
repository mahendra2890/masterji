"""The changelog catches up with the record, the tour's footer and a dropped turn.

Same shape as 0011, 0012, 0016, 0020, 0022, 0025, 0026, 0035, 0036, 0037, 0038,
0039, 0040 and 0041: newest last, so the row created last leads its day under
the model's ("-shipped_on", "-id") ordering.

Written as 0043 off 0042, this branch's own schema migration for
Message.Role.SYSTEM, so the two land in order and the leaf stays single. This
pair has been renumbered twice — 0040/0041 off 0039 when the branch opened,
then 0041/0042 — because 0040_changelog_the_zero_badge_goes_quiet and
0041_changelog_answer_the_question_asked each landed on main while it was open.
That is the normal case here, not bad luck: several sessions branch off the
same main. Check the leaf again immediately before the merge button rather than
before the test run, because two leaves stop main deploying, not just this
branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 10),
        "CHANGED",
        "The record shows your last week, and the rest on request",
        "Every day you had ever recorded was drawn under Today, so the card "
        "grew for exactly as long as you kept turning up — forty days of work "
        "made a wall you had to scroll past to reach anything below it, and "
        "Masterji will hold ninety. It now shows the last seven and says how "
        "many are behind them; one press opens the lot. Nothing was removed, "
        "and the button counts what it is hiding.",
    ),
    (
        date(2026, 8, 10),
        "FIXED",
        "A turn Masterji drops is no longer something he said",
        "When the model fell over before its first word, \"Masterji lost the "
        "thread\" was saved as a message from him — his avatar, his bubble, "
        "sitting in your conversation weeks later looking exactly like "
        "coaching. Worse, it was read back to him on the next turn as his own "
        "words. It is now marked as what it is: a note about the "
        "conversation, drawn apart from it, carrying a button that sends your "
        "message again so you never retype a paragraph a server dropped.",
    ),
    (
        date(2026, 8, 10),
        "CHANGED",
        "The tour's Next button follows you down the page",
        "A slide of the guided tour runs two to four screens on a phone — the "
        "mocks are the app's own cards, so they stack rather than shrink — and "
        "\"Next\" was the last thing on the page. Getting to the next slide "
        "meant scrolling past everything you had just read. It now sits at the "
        "bottom of the screen with the step count beside it, on a deck whose "
        "whole job is to be a short walk to the sign-in button.",
    ),
    (
        date(2026, 8, 10),
        "FIXED",
        "Small controls got bigger, and the header stopped shuffling",
        "\"What's new\", \"close this goal\", the EN/हिं switch and the "
        "footer's source link were all under the 24-pixel minimum a target is "
        "supposed to have — the smallest of them, at fifteen pixels, was the "
        "one that closes your goal. All of them are comfortable now, and none "
        "of them moved anything around them. The run counter also holds one "
        "fixed width whatever number is in it: it used to grow with your "
        "streak and push \"What's new\" onto a different line, so a control "
        "you had learned the position of moved after a good week.",
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
    dependencies = [("coach", "0042_alter_message_role")]
    operations = [migrations.RunPython(seed, unseed)]
