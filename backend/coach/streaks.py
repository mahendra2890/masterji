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


def span(goal: Goal, today: date) -> tuple[date, date]:
    """The goal's first and last day, on ONE calendar.

    `goal.created_at` is a server UTC timestamp while every check-in date is
    the browser's local date, so treating the first as the start drops a day
    for anyone whose clock is ahead of UTC — a builder who worked an evening
    and then past midnight IST closed out to "1 day active · best streak 2",
    which is not a thing that can be true. Widening the span to whatever the
    check-ins already claim puts both ends back on the same calendar without
    trusting the client for anything it can't already write.

    Returns the bounds rather than only their difference because the export
    prints the start date under the goal's title. Deriving that separately gave
    a file headed "Started 13 Aug" above a first entry dated the 9th — the same
    mixed-calendar bug as above, in a document handed to a stranger.
    """
    # Materialised once: a lazy values_list would re-run the query for each
    # of the two bounds below.
    dates = list(goal.checkins.values_list("date", flat=True))
    return min([goal.created_at.date(), *dates]), max([today, *dates])


def days_active(goal: Goal, today: date) -> int:
    """How long the goal has been on the record, counted inclusively.

    Lived in views.py while the closing card was its only reader. It moved here
    when the export became a second one: this is day arithmetic over check-in
    rows, which is what this module is.
    """
    start, end = span(goal, today)
    return (end - start).days + 1


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
