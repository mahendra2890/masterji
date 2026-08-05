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


def best_streak(goal: Goal) -> int:
    """The longest run this goal ever had — kept when it's retired, so the
    record of real work outlives the idea."""
    complete = _complete_dates(goal)
    best = run = 0
    for day in sorted(complete):
        run = run + 1 if (day - timedelta(days=1)) in complete else 1
        best = max(best, run)
    return best


def lifetime_days(user) -> int:
    """Days this builder showed up, across every goal they've ever had.

    The current streak is per-goal and resets on retirement — correct, it is a
    fact about this idea. But a builder whose conversations honestly killed
    their idea after three weeks must not watch the app forget that the three
    weeks happened; that reads as punishment for doing the right thing.
    """
    rows = (
        CheckIn.objects.filter(goal__user=user)
        .exclude(am_declaration="")
        .exclude(pm_proof_text="")
    )
    return len(set(rows.values_list("date", flat=True)))
