"""Does the loop work? Seven counts over rows the server already holds.

Nothing in this repo counted whether the product does what it claims. The only
analytics are `@vercel/analytics` and `@vercel/speed-insights` — pageviews and
web vitals — and `coach/admin.py` registers list displays with no aggregate in
it at all. So the questions the product is built to answer about itself had no
answer, and the backlog was being ranked on argument.

Every number here is a COUNT over rows that already exist. No new tracking, no
events, no third-party pipeline, nothing builder-facing. It reads `gates.py`
and `streaks.py` helpers unchanged and never writes: this readout adds no
authority and can contradict nothing, which is what makes it safe to trust.

Deliberately a command that prints, not a page with charts. With a handful of
real builders every number below is small enough to read out of Django admin,
and a dashboard for n=3 is theatre. The value is not resolution — it is that
choosing what to build next stops being a debate about which argument sounds
better.

Staff-only by being a management command: there is no route to it, so there is
nothing to authorise.
"""

from collections import defaultdict
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from coach import gates, streaks
from coach.models import (
    CheckIn,
    Goal,
    GoalRetirement,
    Phase,
    PhaseTransition,
    Workshop,
)

# The three windows the roadmap's retention questions are asked in.
RETURN_DAYS = (2, 7, 30)


def _pct(part: int, whole: int) -> str:
    """A share, or a dash when the denominator is zero.

    A dash rather than 0%: "nobody came back" and "nobody could have come back
    yet" are different findings, and a young database is full of the second.
    """
    return f"{100 * part / whole:.0f}%" if whole else "—"


def _median(values: list[float]) -> float | None:
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def phase_durations() -> dict[str, list[float]]:
    """Days each goal spent in each phase it has left, per phase.

    Read off `PhaseTransition` rather than `Goal.phase_entered_at`, which only
    knows about the phase a goal is in NOW. Entry into IDEA is the goal's own
    creation — there is no transition into the first rung.

    Only phases a goal has LEFT are counted. A goal sitting in BUILD for three
    weeks has not taken three weeks to clear BUILD; counting it would report a
    number that falls every time somebody new arrives.
    """
    by_goal: dict[int, list[PhaseTransition]] = defaultdict(list)
    for row in PhaseTransition.objects.order_by("created_at"):
        by_goal[row.goal_id].append(row)

    durations: dict[str, list[float]] = defaultdict(list)
    created = dict(Goal.all_objects.values_list("id", "created_at"))
    for goal_id, transitions in by_goal.items():
        entered = created.get(goal_id)
        if entered is None:
            continue
        for row in transitions:
            durations[row.from_phase].append(
                (row.created_at - entered).total_seconds() / 86400
            )
            entered = row.created_at
    return durations


def return_windows(first_days: dict[int, object], all_days: dict[int, set]) -> list:
    """Retention at each window, with the denominator that makes it honest.

    A builder is counted as returning at day N if they have any complete day on
    or after their first one plus N-1 days. The denominator is only builders
    whose first day is far enough back that day N has actually arrived for
    them — otherwise every new signup would quietly drag the number down.
    """
    today = timezone.localdate()
    rows = []
    for window in RETURN_DAYS:
        eligible = came_back = 0
        for user_id, first in first_days.items():
            if (today - first).days < window - 1:
                continue
            eligible += 1
            if any(day >= first + timedelta(days=window - 1) for day in all_days[user_id]):
                came_back += 1
        rows.append((window, came_back, eligible))
    return rows


class Command(BaseCommand):
    help = "Print what the database knows about whether the loop works."

    def line(self, label: str, value):
        self.stdout.write(f"  {label:<44} {value}".rstrip())

    def head(self, title: str):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(title))

    def handle(self, *args, **options):
        User = get_user_model()
        today = timezone.localdate()

        self.stdout.write(
            self.style.SUCCESS(f"Masterji — the loop, as of {today.isoformat()}")
        )

        # --- the room before the goal ---------------------------------------
        # `Workshop.status` IS the conversion: GoalsView.post flips every open
        # workshop to SPENT at the moment a goal is committed, whether or not
        # the title came out of the room. So a spent workshop is exactly a
        # workshop that ended in a committed goal — nothing has to be inferred.
        self.head("The workshop")
        workshops = Workshop.all_objects.count()
        spent = Workshop.all_objects.filter(status=Workshop.Status.SPENT).count()
        self.line("opened", workshops)
        self.line("ended in a committed goal", f"{spent}  ({_pct(spent, workshops)})")
        self.line(
            "still open", Workshop.all_objects.filter(status=Workshop.Status.OPEN).count()
        )

        # --- the ladder ------------------------------------------------------
        self.head("The ladder")
        goals = Goal.objects.count()
        reached = {Phase.IDEA: goals}
        for row in (
            PhaseTransition.objects.values("to_phase")
            .annotate(n=Count("goal", distinct=True))
            .order_by()
        ):
            reached[row["to_phase"]] = row["n"]
        durations = phase_durations()
        for phase in Phase:
            got_there = reached.get(phase, 0)
            median = _median(durations.get(phase, []))
            spent_days = f"median {median:.1f}d to clear" if median is not None else ""
            self.line(
                f"reached {phase.value}",
                f"{got_there:<4} ({_pct(got_there, goals)} of {goals} goals)  {spent_days}",
            )

        # --- the evenings ----------------------------------------------------
        self.head("The evenings")
        checkins = CheckIn.objects.count()
        proved = CheckIn.objects.exclude(pm_proof_text="").count()
        self.line("check-ins", checkins)
        self.line("carried a proof", f"{proved}  ({_pct(proved, checkins)})")
        for status_value, _ in CheckIn.ProofStatus.choices:
            n = CheckIn.objects.filter(proof_status=status_value).count()
            self.line(f"  {status_value}", f"{n}  ({_pct(n, proved)} of proved)")

        # --- what a push-back is actually for --------------------------------
        # The question the product's whole argument rests on: does a refusal
        # send builders back to the work, or out of the door? A check-in with
        # an archived attempt was refused at least once; its status now is what
        # they did about it.
        self.head("After a push-back")
        retried = CheckIn.objects.filter(attempts__isnull=False).distinct()
        refused_once = retried.count()
        won_through = retried.filter(
            proof_status=CheckIn.ProofStatus.ACCEPTED
        ).count()
        self.line("evenings refused at least once", refused_once)
        self.line(
            "…later accepted", f"{won_through}  ({_pct(won_through, refused_once)})"
        )
        self.line(
            "…still refused", refused_once - won_through
        )

        # --- coming back -----------------------------------------------------
        self.head("Coming back")
        complete: dict[int, set] = defaultdict(set)
        for goal in Goal.objects.all():
            complete[goal.user_id] |= streaks._complete_dates(goal)
        first_days = {u: min(days) for u, days in complete.items() if days}
        self.line("builders with at least one complete day", len(first_days))
        for window, came_back, eligible in return_windows(first_days, complete):
            self.line(
                f"still going on day {window}",
                f"{came_back}/{eligible}  ({_pct(came_back, eligible)})",
            )

        # --- how they end ----------------------------------------------------
        # `reads_as` is computed from banked proofs, never claimed — so this is
        # the one honest count of what the product produced.
        self.head("Closed goals")
        retirements = GoalRetirement.objects.select_related("goal")
        verdicts: dict[str, int] = defaultdict(int)
        for retirement in retirements:
            verdicts[gates.reads_as(retirement.goal, retirement.outcome)] += 1
        self.line("closed", retirements.count())
        for verdict, n in sorted(verdicts.items()):
            self.line(f"  {verdict}", n)

        self.head("Accounts")
        self.line("users", User.objects.count())
        self.line("with a goal", Goal.objects.values("user").distinct().count())
        self.stdout.write("")
