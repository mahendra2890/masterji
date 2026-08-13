"""The changelog records that the server now opens the link a proof carries.

Same shape as every changelog migration before it: newest last, so the row
created last leads its day under the model's ("-shipped_on", "-id") ordering.

Depends on 0066, the schema half — there is nowhere to record an answer before
the columns exist.

Builder-visible on the strength of one thing only: the verdict Masterji writes
tonight can now mention the link, so the words on the screen change even though
no control does. That is the boundary case PR #126 raised and the answer on
record was to include it, which is what this file does.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 13),
        "NEW",
        "Masterji opens the link you file",
        "BUILD asks for a link to something running, and until tonight nobody "
        "ever clicked it — the screenshot you attach gets read, but a URL was "
        "taken on trust, so an address you typed from memory looked exactly like "
        "a deploy that works. Now the server opens it before Masterji reads your "
        "proof, and tells him one thing: it answered, or the host said there is "
        "nothing at that address. It is corroboration and nothing more. A link "
        "that answers does not clear the bar on its own — something running is "
        "not somebody using it, which is the whole of what BUILD is asking. And "
        "a link that doesn't answer costs you nothing by itself: he will name it "
        "and ask you for the working address, because a typo, a preview that has "
        "been torn down and a renamed project all look the same from here, and "
        "if what you wrote clears the bar then it clears it. When the check "
        "cannot be made at all — a slow host, a network that drops, a link he is "
        "not allowed to open — he is told nothing rather than something wrong. "
        "The gate is untouched: it counts accepted proofs, exactly as it did "
        "this morning.",
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
    dependencies = [("coach", "0066_proof_link_checked")]
    operations = [migrations.RunPython(seed, unseed)]
