"""Record every accepted proof a retired goal banked, not only the
VALIDATION-onward subset.

`contact_proofs` answers exactly one question — does "the idea was disproved"
hold up — and it understated the work when shown to the builder: someone who
talked to the principal while still in IDEA saw "0 contact proofs", which reads
as "you did nothing". Backfill is exact: retired goals are write-immutable, so
their check-ins can be recounted safely.
"""

from django.db import migrations, models


def backfill_accepted(apps, schema_editor):
    GoalRetirement = apps.get_model("coach", "GoalRetirement")
    CheckIn = apps.get_model("coach", "CheckIn")

    updates = []
    for retirement in GoalRetirement.objects.all():
        retirement.accepted_proofs = CheckIn.objects.filter(
            goal_id=retirement.goal_id, proof_status="ACCEPTED", deleted_at__isnull=True
        ).count()
        updates.append(retirement)

    if updates:
        GoalRetirement.objects.bulk_update(updates, ["accepted_proofs"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("coach", "0005_goal_retirement"),
    ]

    operations = [
        migrations.AddField(
            model_name="goalretirement",
            name="accepted_proofs",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(backfill_accepted, migrations.RunPython.noop),
    ]
