"""Changelog rows for the coaching-voice pass: the thinking-partner mode, the
tone rewrite, and the second-try fix.

Shipped as a data migration rather than typed into the admin for the reason
0011 gives — it applies on deploy, so the entry appears the moment the change
reaches builders instead of whenever someone remembers.

Newest first below, inserted oldest first: the model orders by
("-shipped_on", "-id"), so within a day the row created last leads.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 8),
        "NEW",
        "He writes tonight's proof for you",
        "You'd tell Masterji about the conversation you just had, he'd coach "
        "at you about it, and the evening would end with nothing filed — "
        "because turning what you said into what the proof box wanted was "
        "left to you. Now he watches the conversation against the bar, and "
        "the moment you've told him enough he writes the proof up himself, in "
        "your words and your facts, and asks whether it's right. It appears "
        "in tonight's check-in as a draft: file it, or edit it first. Filed "
        "as he wrote it, it goes straight through — he already decided it "
        "counted, so he doesn't get a second opinion on his own draft. "
        "Nothing is recorded until you file it, and he won't offer at all "
        "while a piece is genuinely missing — he'll ask for that one piece "
        "instead.",
    ),
    (
        date(2026, 8, 8),
        "NEW",
        "Think it through with Masterji",
        "There is work that comes before there is anything to declare — "
        "figuring out who actually has the problem, or which of three ideas "
        "is the one. Masterji was no use for that: every answer came back as "
        "an assignment. The button in the header switches him to a thinking "
        "partner, and he changes sides of the table: questions instead of "
        "demands, two or three concrete options when you're stuck, his own "
        "reasoning out loud so you can disagree with it. The setting stays "
        "with you until you switch it back. What it does not do is move the "
        "gate — phases still open on accepted proofs, and thinking out loud "
        "with you was never going to be a way around that.",
    ),
    (
        date(2026, 8, 8),
        "CHANGED",
        "Assertive, not disrespectful — and he can tell you when you're done",
        "Masterji is meant to be hard to satisfy. He was also, too often, "
        "rude about it, and he had no way to say that something was good "
        "enough — the coach carried the phase's refusals and a proof count "
        "and no definition of 'enough' anywhere in his head, so the only "
        "reply he could build was 'not yet, give me more'. He now reads the "
        "same bar the check-in form shows you, and when your answer meets it "
        "he says so. He also judges what your evidence CONTAINS rather than "
        "the shape you wrote it in — the playbooks describe what has to be "
        "there, not a format you have to reproduce, and you were never "
        "supposed to be tested on how well you'd learned our phrasing. He "
        "still won't discuss your tech stack in IDEA: he'll decline it in one "
        "line and give you the reason, once, instead of a lecture. And when a "
        "piece of real work lands, he names it. Hard on the work, easy on you.",
    ),
    (
        date(2026, 8, 8),
        "FIXED",
        "A second try is judged against the first",
        "Answer a push-back and your new proof was read by a Masterji who "
        "had no memory of what he'd asked for — free to send it back for "
        "some brand-new reason. Builders described it exactly right: you give "
        "him what he asked for and he still doesn't get it. He now sees every "
        "try you've made tonight and the words he sent each one back with, "
        "and he is told plainly that he does not get to raise the bar on a "
        "second look or find a fault he could have named the first time. "
        "After a third refusal he has to stop and answer one question before "
        "judging again: is the work missing, or is the work there and the two "
        "of you failing to understand each other? If it's the second, that's "
        "his failure — he takes it, writes your proof out as he now "
        "understands it, and says what he'd misread. Nobody has to be a good "
        "writer to get credit for work they did. What has not changed: "
        "nothing passes because you submitted it often enough. Work that "
        "isn't there gets refused on the fourth try and the fortieth.",
    ),
]


def seed(apps, schema_editor):
    Entry = apps.get_model("coach", "ChangelogEntry")
    for shipped_on, kind, title, body in reversed(SEED):
        Entry.all_objects.get_or_create(
            shipped_on=shipped_on,
            title=title,
            defaults={"kind": kind, "body": body, "is_active": True},
        )


def unseed(apps, schema_editor):
    Entry = apps.get_model("coach", "ChangelogEntry")
    Entry.all_objects.filter(title__in=[title for _, _, title, _ in SEED]).delete()


class Migration(migrations.Migration):
    dependencies = [("coach", "0011_seed_changelog")]
    operations = [migrations.RunPython(seed, unseed)]
