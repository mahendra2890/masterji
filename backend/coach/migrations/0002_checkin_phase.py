"""Stamp each check-in with the phase its work belonged to.

Backfilling from `date` would be wrong — dates come from the client's local
clock. `created_at` is a server timestamp, same clock as PhaseTransition, so
"which phase was this goal in when the row was created" is answerable exactly.
"""

from django.db import migrations, models


def backfill_phase(apps, schema_editor):
    CheckIn = apps.get_model("coach", "CheckIn")
    PhaseTransition = apps.get_model("coach", "PhaseTransition")

    transitions_by_goal: dict[int, list[tuple]] = {}
    for t in PhaseTransition.objects.order_by("created_at").values_list(
        "goal_id", "created_at", "from_phase", "to_phase"
    ):
        transitions_by_goal.setdefault(t[0], []).append(t[1:])

    updates = []
    for checkin in CheckIn.objects.all():
        history = transitions_by_goal.get(checkin.goal_id, [])
        # Before the first transition the goal sat in that transition's
        # from_phase; each transition it predates leaves it in that to_phase.
        phase = history[0][1] if history else "IDEA"
        for created_at, _from_phase, to_phase in history:
            if checkin.created_at < created_at:
                break
            phase = to_phase
        checkin.phase = phase
        updates.append(checkin)

    if updates:
        CheckIn.objects.bulk_update(updates, ["phase"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("coach", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="checkin",
            name="phase",
            field=models.CharField(
                blank=True,
                choices=[
                    ("IDEA", "Idea"),
                    ("VALIDATION", "Validation"),
                    ("BUILD", "Build"),
                    ("LAUNCH", "Launch"),
                ],
                max_length=12,
            ),
        ),
        migrations.RunPython(backfill_phase, migrations.RunPython.noop),
    ]
