"""Streak = consecutive days with a complete loop (declared AND proved).

Today only counts once it's complete, so an in-progress day never shows a
broken streak at breakfast.
"""

from datetime import date, timedelta

from .models import CheckIn, Goal


def _complete_dates(goal: Goal) -> set[date]:
    rows = CheckIn.objects.filter(goal=goal).exclude(am_declaration="").exclude(
        pm_proof_text=""
    )
    return set(rows.values_list("date", flat=True))


def current_streak(goal: Goal, today: date) -> int:
    complete = _complete_dates(goal)
    day = today if today in complete else today - timedelta(days=1)
    streak = 0
    while day in complete:
        streak += 1
        day -= timedelta(days=1)
    return streak
