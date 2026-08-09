"""The changelog catches up with three fixes to where the evening happens.

Same shape as 0011, 0012, 0016, 0020, 0022 and 0025: newest last, so the row
created last leads its day under the model's ("-shipped_on", "-id") ordering.

Single leaf at write time (0025). Check again before merging — three sessions
have collided on this file already, and two leaves stop main deploying rather
than just this branch.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "FIXED",
        "The chat stops saying your evening is worth nothing",
        "While Masterji writes tonight's proof out of your conversation, the "
        "line under the reply box still read \"nothing here counts\" — which "
        "is the rule, and was the wrong half of it to say on its own. He is "
        "writing your words down as you say them; being told you are wasting "
        "your breath while that happens is exactly backwards. It now says he "
        "has it and how many pieces are still needed, and keeps the rule that "
        "filing is yours. On a phone the Today tab says \"notes\" too, so you "
        "can see it without leaving the conversation.",
    ),
    (
        date(2026, 8, 9),
        "CHANGED",
        "His draft comes before the rules now",
        "The evening card asked what tonight needs, then showed you what he "
        "had already written from your conversation — the question above the "
        "answer, with the answer's button set in the smallest type on the "
        "card while Submit, the step after it, got the big one. His draft is "
        "first now and its button is a real button, and it drops you straight "
        "into the box it fills. When the draft already clears the bar the "
        "full ask folds away, because by then it is something to check "
        "against rather than something to read.",
    ),
    (
        date(2026, 8, 9),
        "FIXED",
        "The reply box gives the conversation room back on a small phone",
        "Four rows was measured on a tall screen. On a 667px phone it left "
        "the chat 181 pixels — less than two messages, and a box to type in "
        "that was bigger than the conversation it was for. Short screens get "
        "two rows now; longer replies scroll inside it exactly as they did. "
        "Nothing changes on a tall one.",
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
    dependencies = [("coach", "0025_changelog_reply_box_holds_four_lines")]
    operations = [migrations.RunPython(seed, unseed)]
