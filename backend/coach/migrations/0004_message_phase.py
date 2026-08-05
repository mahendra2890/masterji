"""Stamp each message with the phase the conversation was in.

Same reasoning as 0002 for check-ins: reading the phase off the goal reports
today's phase for a message written weeks ago. Backfill from `created_at`,
which shares the server clock with PhaseTransition, so the inference is exact.
"""

from django.db import migrations, models


def backfill_phase(apps, schema_editor):
    Message = apps.get_model("coach", "Message")
    PhaseTransition = apps.get_model("coach", "PhaseTransition")

    transitions_by_goal: dict[int, list[tuple]] = {}
    for t in PhaseTransition.objects.order_by("created_at").values_list(
        "goal_id", "created_at", "from_phase", "to_phase"
    ):
        transitions_by_goal.setdefault(t[0], []).append(t[1:])

    updates = []
    for message in Message.objects.all():
        history = transitions_by_goal.get(message.goal_id, [])
        phase = history[0][1] if history else "IDEA"
        for created_at, _from_phase, to_phase in history:
            if message.created_at < created_at:
                break
            phase = to_phase
        message.phase = phase
        updates.append(message)

    if updates:
        Message.objects.bulk_update(updates, ["phase"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("coach", "0003_multiple_cycles_per_day"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
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
