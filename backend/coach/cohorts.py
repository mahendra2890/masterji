"""A cohort board: forty builders' counted work, in a fixed number of queries.

Every column here is a server count the product already keeps —
`accepted_proofs_total`, `contact_proofs`, the current streak, the phase
reached. Nothing self-reported appears on it: not the goal's title, not a
proof's text, not a retirement's reason, not one word the builder typed.
That is the competitive argument in one sentence — NEC and NSRCEL cohorts rank
on jury-judged self-reports and pitch milestones, so the loudest deck wins, and
this board has no field a deck can be written in.

**Two rules this module exists to hold at once.**

*Tenancy is by membership, in the queryset.* `joined()` is the only door, and
every other function here takes what it returns. A builder who has not joined a
cohort cannot reach it by id, by code, or by being counted inside somebody
else's aggregate.

*The count is computed once.* `gates.py` is not touched and is not called per
member: forty `gates.accepted_proofs_total(goal)` calls are forty queries, on a
free-tier instance with one worker and 0.1 CPU. So the counting is one grouped
query — and what stops that from becoming a second, quietly disagreeing
definition of the same number is that it is built from `gates`' own constants
(`gates.CONTACT_PHASES`, `CheckIn.ProofStatus.ACCEPTED`), and that
`CohortCountsAgreeTests` asserts per-goal equality with
`gates.accepted_proofs_total`, `gates.contact_proofs` and
`streaks.current_streak` over a spread of fixtures. A count computed twice will
disagree with itself eventually; a count computed twice with a test between
them says so out loud the day it starts.

**Indexes.** None are added, and the plans were read rather than assumed —
0071's own discipline, since the thing that breaks silently is the *match*
between an index and the query it was built for.

- The active-goal lookup takes `coach_goal_active_idx` as-is: it leads with
  `user`, and this asks for forty of them.
- Both check-in reads go through the implicit index on `goal_id`, and NOT
  through `coach_checkin_gate_idx`. That index is `(goal, phase, proof_status)`
  and this filters goal and `proof_status` without naming a phase, so `phase`
  sits in the middle and only the `goal` prefix is usable — which is exactly
  what the plain foreign-key index already gives, on narrower rows. An index on
  `(goal, proof_status)` would fit better on paper and would earn nothing here:
  both of these reads are "every check-in belonging to these goals", so the rows
  have to be visited either way and the status is a residual over rows already
  in hand. 0071's lesson is that an index which is not on a named query is dead
  weight, and a fourth one leading with the same column is that twice.

What was worth fixing is in `_streaks`: the model's default ordering was
sorting every row the cohort has ever written, to build sets that have no order.
"""

from collections import defaultdict
from datetime import date

from django.db.models import Count, Q

from . import gates, streaks
from .models import CheckIn, Cohort, CohortMember, Goal, Phase

# Where a member sorts on the board, most significant first. Contact proofs
# lead because they are the question the coordinator actually has — which of
# these forty talked to somebody this week — and every one of them had to clear
# a gate stamped VALIDATION or later. Ties fall through to total work banked,
# then to showing up, then to how far up the ladder the goal is.
#
# A tuple of counts and nothing else. There is no weighting to argue about and
# no field a builder can raise by writing something.
RANK_KEYS = ("contact_proofs", "accepted_proofs", "streak", "phase_index")


def joined(user):
    """The cohorts this builder is currently in. The only door into any of this.

    Returned as a queryset of `Cohort`, annotated with how many members each
    has, so the caller never touches `CohortMember` again.

    The `members__deleted_at__isnull=True` on the count is not belt-and-braces.
    `SoftDeleteManager` puts its predicate on the model being *queried* and
    never on a reverse join, so without it every builder who ever left would
    still be counted in the size of the board they left.

    The membership filter is a subquery (`id__in=…`) rather than a join for a
    second reason, and it is a Django trap worth naming: filtering and
    annotating across the same reverse relation reuses one join, which would
    make `size` count only the rows that matched the filter — every board would
    report exactly one member, and it would look right on a one-member fixture.
    """
    mine = CohortMember.objects.filter(user=user).values_list("cohort_id", flat=True)
    return Cohort.objects.filter(id__in=mine).annotate(
        size=Count("members", filter=Q(members__deleted_at__isnull=True))
    )


def mine(user, pk: int) -> Cohort | None:
    """One cohort, if this builder is in it, and None in every other case.

    Deliberately does not distinguish "no such cohort" from "not yours" — the
    caller 404s both, the way `SharedRecordView` refuses a wrong slug and a
    revoked one identically. The difference between those two answers is itself
    something somebody can walk to find out which cohorts exist.
    """
    return joined(user).filter(pk=pk).first()


def _proof_counts(goal_ids: list[int]) -> dict[int, tuple[int, int]]:
    """Accepted proofs per goal, and the contact subset, in ONE query.

    The two numbers `gates.accepted_proofs_total` and `gates.contact_proofs`
    return for a single goal, grouped instead of asked forty times. Both read
    the same accepted rows, so they are one aggregate with a filtered count
    rather than two passes over the table.

    `.order_by()` is load-bearing: `CheckIn.Meta.ordering` is `["-date"]`, and
    Django appends a model's default ordering to the GROUP BY of a `values()`
    aggregate — which would group by (goal, date) and return one row per day
    per goal. The counts would then be 1 across the board, on a fixture with
    one proof a day, which is what every fixture looks like.
    """
    if not goal_ids:
        return {}
    rows = (
        CheckIn.objects.filter(
            goal_id__in=goal_ids, proof_status=CheckIn.ProofStatus.ACCEPTED
        )
        .values("goal_id")
        .annotate(
            total=Count("id"),
            contact=Count("id", filter=Q(phase__in=gates.CONTACT_PHASES)),
        )
        .order_by()
    )
    return {row["goal_id"]: (row["total"], row["contact"]) for row in rows}


def _streaks(goal_ids: list[int], today: date) -> dict[int, int]:
    """Current streak per goal, from ONE read of every complete day.

    Same definition of a complete day as `streaks._complete_dates` — declared
    AND proved — and the same walk over it, because the walk is
    `streaks.streak_from` and there is only one of it. What is different is the
    shape of the read: forty goals' days in a single query, bucketed here.

    Not bounded to a recent window. A cap would make a long streak read short
    for exactly the builder who earned it, and the rows are two small columns
    over the cohort's own goals — one query either way.
    """
    if not goal_ids:
        return {}
    complete: dict[int, set[date]] = defaultdict(set)
    rows = (
        CheckIn.objects.filter(goal_id__in=goal_ids)
        .exclude(am_declaration="")
        .exclude(pm_proof_text="")
        .values_list("goal_id", "date")
        # `.order_by()` for the second time in this file, and here it is not a
        # correctness fix but a free one. `CheckIn.Meta.ordering` is `["-date"]`,
        # so without it every row the cohort has ever written goes through a
        # sort — `USE TEMP B-TREE FOR ORDER BY` in the plan — to build sets,
        # which have no order. Measured on a 40-member fixture with four months
        # of evenings each: the sort is over all 4,800 rows and buys nothing.
        .order_by()
    )
    for goal_id, day in rows:
        complete[goal_id].add(day)
    return {
        goal_id: streaks.streak_from(complete[goal_id], today) for goal_id in goal_ids
    }


def _display_name(user) -> str:
    """What a peer sees. A first name, or the username it falls back to.

    Never the email address. A builder agreed to be counted where their cohort
    can see it; they did not hand out a way to contact them, and the board has
    no reason to carry one.
    """
    return user.first_name.strip() or user.username


def _rank(rows: list[dict]) -> None:
    """Standard competition ranking, over the rows that have a goal.

    Ties share a place and the next one skips — two builders on identical
    counts are not fourth and fifth, and picking one of them to be fourth would
    be the board inventing a difference the record does not contain.

    Members with no active goal are ranked `None` rather than last. They have
    nothing on the board to be ranked on, and a coordinator sitting in their
    own cohort reading "39th, 0 proofs" is the board making a judgement out of
    an absence. Mutates in place; the caller has already sorted.
    """
    place = 0
    previous = None
    for i, row in enumerate(r for r in rows if r["has_goal"]):
        key = tuple(row[k] for k in RANK_KEYS)
        if key != previous:
            place = i + 1
            previous = key
        row["rank"] = place


def board(cohort: Cohort, today: date) -> list[dict]:
    """Every member of one cohort, ranked, as counts and nothing else.

    Four queries, whatever the cohort's size: the members, their active goals,
    one grouped proof count, one read of complete days. `CohortBoardQueryTests`
    pins that with `assertNumQueries` at two cohort sizes, because a number in
    a docstring is a claim and an N+1 reintroduced by a later `select_related`
    that somebody removed would not otherwise be noticed until production.

    Which goal a row reports is the builder's ACTIVE one — the only one the
    product allows at a time. A member between ideas shows as having none,
    rather than being hidden or backfilled from a retired goal: "closed their
    idea last week" and "three weeks into VALIDATION" are different facts, and
    a board that blurred them would be worse than no board.
    """
    members = list(
        CohortMember.objects.filter(cohort=cohort)
        .select_related("user")
        .order_by("joined_at")
    )
    if not members:
        return []

    goals = {
        goal.user_id: goal
        for goal in Goal.objects.filter(
            user_id__in=[m.user_id for m in members], status=Goal.Status.ACTIVE
        )
    }
    goal_ids = [goal.id for goal in goals.values()]
    counts = _proof_counts(goal_ids)
    runs = _streaks(goal_ids, today)

    rows = []
    for member in members:
        goal = goals.get(member.user_id)
        total, contact = counts.get(goal.id, (0, 0)) if goal else (0, 0)
        rows.append(
            {
                "name": _display_name(member.user),
                "has_goal": goal is not None,
                "phase": goal.phase if goal else None,
                # Where that phase sits on the ladder, so the client sorts and
                # the server ranks on the same number rather than on a string
                # somebody has to know the order of. -1 for no goal, which
                # never reaches a comparison — those rows are not ranked.
                "phase_index": (
                    gates.PHASE_ORDER.index(Phase(goal.phase)) if goal else -1
                ),
                "accepted_proofs": total,
                "contact_proofs": contact,
                "streak": runs.get(goal.id, 0) if goal else 0,
                "rank": None,
            }
        )

    # Goal-less rows last, then the counts descending. Ties keep the order they
    # arrived in, which is `joined_at`, because Python's sort is stable and the
    # members were read that way — a deliberate tiebreak rather than a leftover:
    # it is not a fact about the work, and it means two identical records read
    # the same way on every load instead of swapping places.
    rows.sort(
        key=lambda row: (
            not row["has_goal"],
            *(-row[k] for k in RANK_KEYS),
        )
    )
    _rank(rows)
    return rows
