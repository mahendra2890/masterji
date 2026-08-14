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


def last_complete_date(goal: Goal) -> date | None:
    """The newest day this goal declared AND proved, or None if there is none.

    Same set the streak is counted from, deliberately: the state block states
    both, and a "last complete day" that meant something other than what
    "consecutive complete days" counts would be two lines contradicting each
    other under a heading that says to trust them.
    """
    return max(_complete_dates(goal), default=None)


def streak_from(complete: set[date], today: date) -> int:
    """The walk itself, over a set of complete days somebody else assembled.

    Split out of `current_streak` for exactly one caller: `coach/cohorts.py`
    reads forty builders' complete days in ONE query and then needs this
    arithmetic per goal, and calling `current_streak` forty times is the N+1
    that whole module exists to avoid. What it must not do is own a second copy
    of the walk — a cohort board that disagreed with the builder's own
    dashboard about their streak would discredit both, and this product's whole
    argument is that the record is true.

    So there is one implementation and two ways in. Nothing about the rule
    moved: today only counts once it is complete, so an in-progress day never
    shows a broken streak at breakfast.
    """
    day = today if today in complete else today - timedelta(days=1)
    streak = 0
    while day in complete:
        streak += 1
        day -= timedelta(days=1)
    return streak


def current_streak(goal: Goal, today: date) -> int:
    return streak_from(_complete_dates(goal), today)


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


def days_in_phase(goal: Goal, today: date) -> int:
    """How long the CURRENT phase has been open, on the builder's calendar.

    The same collision `span` documents, with less to fix it with: there is no
    row carrying the local date a phase was entered on, only `phase_entered_at`,
    which is a server UTC timestamp. So a builder BEHIND UTC can have a phase
    stamped on a date their own calendar has not reached — clamped to 0 here, so
    the first day of a phase reads as its first day rather than as minus one. A
    builder AHEAD of UTC who advanced after local midnight keeps a count one day
    high for the life of that phase; that one is left standing, because the
    alternatives are inventing a timezone for them or storing a date nothing
    else needs, and one day of drift on "three weeks in VALIDATION" changes no
    sentence the coach would say.

    Read twice per turn — the coach's state block and the goal card both quote
    it — which is the reason it is one function rather than a subtraction at
    each end.
    """
    return max(0, (today - goal.phase_entered_at.date()).days)


def days_since_complete(goal: Goal, today: date) -> int | None:
    """Days since the last day that was declared AND proved; None if never.

    No calendar collision to manage, unlike the two above: CheckIn.date is
    already the builder's own local date, so both ends of this subtraction are
    on one. Clamped at 0 all the same, because the ends can still come from two
    — views._client_day falls back to the server's UTC date when the query
    string is garbled, and for a builder ahead of UTC their own rows can be
    dated past it. A negative gap is not a thing to hand a coach.
    """
    last = last_complete_date(goal)
    return None if last is None else max(0, (today - last).days)


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
