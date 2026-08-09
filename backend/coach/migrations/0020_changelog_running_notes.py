"""The changelog catches up with Masterji keeping notes as you talk.

Same shape as 0011, 0012, 0016 and 0018: newest last, so the row created last
leads its day under the model's ("-shipped_on", "-id") ordering.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 9),
        "FIXED",
        "He stops asking for what you already told him",
        "The complaint, and it was the loudest one: you name three things your "
        "customer said, in one sentence, and he answers \"that's one, not "
        "three\" — then asks for all of it again, twice. He now writes tonight's "
        "proof down as you talk instead of holding it in his head until the "
        "end. What he has so far shows up under Today as notes, with the "
        "pieces still owed listed under it, and anything in those notes is "
        "banked: he is not allowed to ask you for it a second time, in chat or "
        "when you file. The counting also stopped being his. He hands over the "
        "pieces one by one — each thing said is its own entry — and the server "
        "does the arithmetic, so \"1 more thing they said\" is a subtraction "
        "and not his reading of his own paragraph. When you tell him he has "
        "misread you, re-reading is his job, not yours to work around. Notes "
        "are not a pass: only a draft with nothing missing files straight "
        "through, a short one filed anyway is judged on its merits like any "
        "other proof, and the gate counts exactly what it counted before.",
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
    dependencies = [("coach", "0019_checkin_proof_missing")]
    operations = [migrations.RunPython(seed, unseed)]
