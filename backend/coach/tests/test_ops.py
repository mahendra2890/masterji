"""The backend's own guards: every table has an admin reader, one migration
leaf, the four indexes, a blank DATABASE_URL refused rather than quietly
replaced, and multi-write paths landing whole or not at all.
"""

from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.apps import apps
from django.contrib import admin
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase

from config import settings as settings_module

from .. import admin as coach_admin
from .. import (
    gates,
    views,
)
from ..management.commands import check_migration_leaf
from ..models import (
    ChangelogEntry,
    CheckIn,
    Goal,
    GoalRetirement,
    Phase,
    PhaseTransition,
    ProofAttempt,
    Workshop,
    WorkshopMessage,
)
from .base import CoachTestCase, make_user


class AdminReachTests(TestCase):
    """Every table in this app has a reader, and the workshop's is the only one.

    A goal's chat is readable in the product, so its rows having no admin page
    would cost nothing. The workshop's is readable nowhere: the room leaves the
    no-goal screen the moment a goal is committed (the commit spends it), and
    nothing shows a spent one back to anybody. So the idea discussions on the
    home screen were being written, kept, and read by no one.
    """

    def test_every_coach_table_is_reachable_from_the_admin(self):
        """Pinned as a rule rather than as two names, because the omission this
        fixes is the kind that recurs: a model lands with its views, its
        serializer and its tests, and admin.py is the file nobody remembers.
        Workshop and WorkshopMessage were the only two it had happened to."""
        unreachable = sorted(
            model.__name__
            for model in apps.get_app_config("coach").get_models()
            if model not in admin.site._registry
        )
        self.assertEqual(unreachable, [])

    def test_the_transcript_shows_every_turn_including_deleted_ones(self):
        """The house rule is that admin sees every row (common/soft_delete.py),
        and an inline is where it silently stops being true — a formset reads
        the default manager, which hides soft-deleted rows. A conversation with
        a hole in it and no mark where the hole is misinforms the only reader
        the room has."""
        workshop = Workshop.objects.create(user=make_user("wanda"))
        kept = WorkshopMessage.objects.create(
            workshop=workshop, role=WorkshopMessage.Role.USER, content="kept"
        )
        gone = WorkshopMessage.objects.create(
            workshop=workshop, role=WorkshopMessage.Role.COACH, content="deleted"
        )
        gone.delete()  # soft

        inline = coach_admin.WorkshopMessageInline(Workshop, admin.site)
        shown = set(inline.get_queryset(None).values_list("id", flat=True))
        self.assertEqual(shown, {kept.id, gone.id})

    def test_the_turn_column_counts_what_the_meter_counts(self):
        """The column is read as "is this room spent" — so it has to be the
        server's own count (views._turns_used: USER rows, undeleted) and not
        a count of the transcript, which includes the coach's half."""
        workshop = Workshop.objects.create(user=make_user("wendell"))
        for role, content in [
            (WorkshopMessage.Role.USER, "one"),
            (WorkshopMessage.Role.COACH, "not a turn"),
            (WorkshopMessage.Role.SYSTEM, "also not a turn"),
            (WorkshopMessage.Role.USER, "two"),
        ]:
            WorkshopMessage.objects.create(
                workshop=workshop, role=role, content=content
            )
        spent = WorkshopMessage.objects.create(
            workshop=workshop, role=WorkshopMessage.Role.USER, content="withdrawn"
        )
        spent.delete()  # soft

        model_admin = admin.site._registry[Workshop]
        row = model_admin.get_queryset(None).get(pk=workshop.pk)
        self.assertEqual(model_admin.turns(row), views._turns_used(workshop))
        self.assertEqual(model_admin.turns(row), 2)


class MigrationLeafTests(SimpleTestCase):
    """The check that used to live only in a session's memory.

    Two sessions each add a migration, each correctly numbered against the main
    it branched from, and together they are two leaf nodes: `migrate` refuses to
    guess and the deploy stops. WORKFLOW.md counts the scar tissue — `0012`
    twice, `0015` three times, `0018` twice, three merge migrations to rejoin
    them. What fixed it was writing the rule into persistent memory, which holds
    exactly as long as every future session remembers to run it. A test holds
    without being remembered, and this suite is already the thing that runs.

    Reads the graph off disk (`MigrationLoader(None)`), so it never touches a
    database and never needs one.
    """

    def test_the_migration_graph_has_one_leaf_per_app(self):
        """The ratchet. When this fails, `migrate` on main is about to."""
        loader = MigrationLoader(None, ignore_no_migrations=True)
        self.assertEqual(
            check_migration_leaf.multi_leaf_apps(loader.graph.leaf_nodes()), {}
        )

    def test_a_second_leaf_is_reported_with_both_names(self):
        """Both names, because the fix is to renumber ONE of them onto the
        other and a message naming only the app leaves you diffing to find
        out which two collided."""
        found = check_migration_leaf.multi_leaf_apps(
            [("coach", "0064_b"), ("coach", "0064_a"), ("accounts", "0003_x")]
        )
        self.assertEqual(found, {"coach": ["0064_a", "0064_b"]})

    def test_one_leaf_each_is_not_a_finding(self):
        """Every app in a healthy graph has exactly one, and Django's own
        apps are in that graph too — a check that flagged them would be
        noise nobody reads."""
        self.assertEqual(
            check_migration_leaf.multi_leaf_apps(
                [("coach", "0064_x"), ("accounts", "0003_x")]
            ),
            {},
        )

    def test_the_command_names_the_coach_leaf_it_approved(self):
        """Printing the name is what makes the pass reviewable: the leaf it
        approved is the one you compare against main's."""
        out = StringIO()
        call_command("check_migration_leaf", stdout=out)
        self.assertIn("coach", out.getvalue())

    def test_the_command_fails_the_build_rather_than_warning(self):
        """A warning in a log nobody opens is the state this already was.
        CommandError is a non-zero exit, which is the only thing CI reads."""
        with mock.patch.object(
            check_migration_leaf, "multi_leaf_apps",
            return_value={"coach": ["0064_a", "0064_b"]},
        ):
            with self.assertRaises(CommandError) as caught:
                call_command("check_migration_leaf")
        message = str(caught.exception)
        self.assertIn("0064_a", message)
        self.assertIn("0064_b", message)


# --- which database a command opens ------------------------------------------


class DatabaseUrlTests(SimpleTestCase):
    """Decided from the env value alone, so it is readable without a boot.

    The trap this closes: `DATABASE_URL="$PROD_NEON_URL" manage.py loop_report`
    with PROD_NEON_URL never exported. The prefix expands to blank, blank used
    to read as "no env value", and a report aimed at production opened an
    unmigrated local SQLite file instead — reporting itself twelve frames deep
    as `no such table: coach_workshop`, which names neither DATABASE_URL nor
    SQLite and reads as a migration problem in the app.
    """

    def test_no_env_value_opens_the_local_sqlite_file(self):
        """Absent has to keep working: it is the documented local path and the
        one CI runs on. Spaces in the path survive — this project's own checkout
        sits under `Personal Projects`, so stripping them breaks every run.
        """
        self.assertEqual(
            settings_module.db_url_or_sqlite(
                None, Path("/Personal Projects/db.sqlite3")
            ),
            "sqlite:////Personal Projects/db.sqlite3",
        )

    def test_a_pasted_connection_string_loses_its_whitespace(self):
        self.assertEqual(
            settings_module.db_url_or_sqlite(
                "postgresql://u:p@host\n  /db?sslmode=require", Path("/db.sqlite3")
            ),
            "postgresql://u:p@host/db?sslmode=require",
        )

    def test_set_but_empty_stops_the_boot(self):
        with self.assertRaises(ImproperlyConfigured) as caught:
            settings_module.db_url_or_sqlite("", Path("/db.sqlite3"))
        message = str(caught.exception)
        self.assertIn("DATABASE_URL is set but empty", message)
        # The message has to name the cause, not only the symptom: the whole
        # cost of the old behaviour was an error that pointed somewhere else.
        self.assertIn("unset", message)

    def test_whitespace_only_stops_the_boot_too(self):
        """It lands in the same place as empty rather than one frame later: the
        strip runs first, so a space-only value would reach the parser as "".
        """
        with self.assertRaises(ImproperlyConfigured):
            settings_module.db_url_or_sqlite(" \n\t ", Path("/db.sqlite3"))


# --- the first indexes in the project ----------------------------------------


class IndexTests(TestCase):
    """The four hot queries reach the four indexes built for them.

    Asserted through the query planner rather than by reading `Meta.indexes`
    back, which would only prove the file says what the file says. What can
    actually break here is the *match*: reorder the fields, drop the partial
    condition so it stops lining up with `SoftDeleteManager`'s
    `deleted_at IS NULL`, or add a filter that defeats the prefix, and the
    index silently stops being used while every test still passes.

    Honest about what this is: the suite runs on SQLite and production is
    Postgres, so this pins that the index *fits* the query, not that Postgres
    will choose it against real statistics. The regression it catches — an
    index quietly orphaned by a change to the query it was built for — is the
    same on both.

    The record here is long on purpose, and `ANALYZE` is the reason it has to
    be. On a one-row table the planner cannot tell `coach_checkin_gate_idx`
    from `coach_checkin_day_idx` — both lead with `goal` — and it picks the
    wrong one. That is not a flaw in the index; it is the issue's own argument
    made visible. None of this matters at today's row counts, and the builder
    who first makes it matter is the one with the longest record, which is to
    say the product's best user.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("indexed")
        cls.goal = Goal.objects.create(user=cls.user, title="Ship something")
        # Other builders, each with the one active goal the constraint allows
        # and a couple of retired ones. Without them `coach_goal` is a
        # one-row table and scanning it is genuinely the right plan — the
        # index is for the database this product wants to have.
        for i in range(40):
            other = make_user(f"builder{i}")
            Goal.objects.create(user=other, title="Theirs")
            for j in range(2):
                Goal.objects.create(
                    user=other, title=f"Closed {j}", status=Goal.Status.ABANDONED
                )
        # Four months of evenings, most of them stamped with phases the goal
        # has already left — which is exactly the shape that makes filtering on
        # (phase, proof_status) worth an index rather than a scan of the goal.
        for i in range(120):
            CheckIn.objects.create(
                goal=cls.goal,
                date=date.today() - timedelta(days=i),
                phase=Phase.VALIDATION if i % 4 else cls.goal.phase,
                am_declaration="talk to a customer",
                pm_proof_text="notes",
                proof_status=(
                    CheckIn.ProofStatus.ACCEPTED
                    if i % 3
                    else CheckIn.ProofStatus.PUSHED_BACK
                ),
            )
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE")

    def test_the_gates_own_query_uses_the_gate_index(self):
        """`gates._banked` runs on every state load, every chat turn and every
        advance. It is the query a refusal is computed from, so it is the one
        query in the product that is never not on the critical path."""
        self.assertIn("coach_checkin_gate_idx", gates._banked(self.goal).explain())

    def test_the_days_check_in_lookups_use_the_day_index(self):
        """`_open_checkin`, `_latest_checkin`, `_carried_over` and
        `_offer_target` all filter (goal, date) and take the newest by
        `-created_at`. The sort column is in the index, so the newest is the
        first row read rather than a sort over the matches."""
        plan = (
            CheckIn.objects.filter(goal=self.goal, date=date.today())
            .order_by("-created_at")
            .explain()
        )
        self.assertIn("coach_checkin_day_idx", plan)
        # The point of carrying `-created_at`: no separate sort step.
        self.assertNotIn("TEMP B-TREE", plan.upper())

    def test_finding_the_active_goal_uses_the_active_goal_index(self):
        """`views._active_goal` runs before almost every authenticated request
        in the product."""
        plan = Goal.objects.filter(
            user=self.user, status=Goal.Status.ACTIVE
        ).explain()
        self.assertIn("coach_goal_active_idx", plan)

    def test_the_public_changelog_uses_the_changelog_index(self):
        """The only unauthenticated endpoint in the product, mounted by every
        screen including the signed-out landing page and the tour, on a table
        whose row count only goes one way."""
        plan = ChangelogEntry.objects.filter(is_active=True).explain()
        self.assertIn("coach_changelog_live_idx", plan)

    def test_a_soft_deleted_row_is_outside_every_one_of_them(self):
        """Why all four are partial. The condition is exactly the predicate
        `SoftDeleteManager` puts on every query, so the index holds only rows
        the product can ever read — and indexing `deleted_at` on its own would
        not have done this job, because nearly every row is undeleted and an
        index that matches nearly everything is not worth reading."""
        banked = gates._banked(self.goal)
        before = banked.count()
        banked.first().delete()
        self.assertEqual(gates._banked(self.goal).count(), before - 1)
        self.assertEqual(CheckIn.all_objects.filter(goal=self.goal).count(), 120)


# --- multi-write paths land whole or not at all ------------------------------


class AtomicWriteTests(CoachTestCase):
    r"""Three places wrote two rows with no transaction around them.

    `grep -rn "transaction.atomic\|select_for_update" backend` returned zero
    outside `.venv` before this. Each test kills the second write and asserts
    the first one did not survive it — because a half-written record is the one
    failure this product cannot absorb: its whole claim is that the record is
    trustworthy because the server wrote it, and nothing here would ever detect
    a row that quietly disagrees with its neighbour.
    """

    def test_a_lost_transition_row_takes_the_advance_with_it(self):
        """The one that matters most. `PhaseTransition` is what the stepper,
        the phase drill-in and `ClosedIdea` read: a goal sitting in VALIDATION
        with no IDEA→VALIDATION row is a record disagreeing with itself, and
        the phase is the half that cannot be reconstructed."""
        goal = self.make_goal()
        self.accept_proofs(goal, gates.PROOFS_REQUIRED[Phase.IDEA].n)
        with mock.patch.object(
            PhaseTransition.objects, "create", side_effect=IntegrityError("boom")
        ):
            with self.assertRaises(IntegrityError):
                gates.try_advance(goal)
        goal.refresh_from_db()
        self.assertEqual(goal.phase, Phase.IDEA)
        self.assertEqual(PhaseTransition.objects.filter(goal=goal).count(), 0)

    def test_a_retirement_that_cannot_be_saved_leaves_the_goal_open(self):
        """The other order of the same bug. A retirement row against a goal
        still marked ACTIVE is worse than it looks: `one_active_goal_per_user`
        means that builder cannot start anything else either."""
        goal = self.make_goal()
        with mock.patch.object(
            Goal, "save", side_effect=IntegrityError("boom")
        ):
            with self.assertRaises(IntegrityError):
                self.client.post(
                    f"/api/coach/goals/{goal.id}/retire/", {"reason": "it died"}
                )
        goal.refresh_from_db()
        self.assertEqual(goal.status, Goal.Status.ACTIVE)
        self.assertEqual(GoalRetirement.objects.filter(goal=goal).count(), 0)

    def test_an_archived_try_never_outlives_the_proof_that_replaced_it(self):
        """A refused try reaches the trail only when the row replacing it
        lands. Otherwise the builder's evening reads as still pushed back, with
        the old text under it, and the trail carries a duplicate of it."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Ramesh"})
        checkin = CheckIn.objects.get(goal=goal)
        checkin.pm_proof_text = "I plan to talk to them"
        checkin.proof_status = CheckIn.ProofStatus.PUSHED_BACK
        checkin.save()

        with mock.patch(
            "coach.views.llm.complete",
            return_value='{"verdict": "accept", "reaction": "ok"}',
        ):
            with mock.patch.object(
                CheckIn, "save", side_effect=IntegrityError("boom")
            ):
                with self.assertRaises(IntegrityError):
                    self.client.post(
                        "/api/coach/checkins/prove/", {"text": "Spoke to Ramesh."}
                    )
        checkin.refresh_from_db()
        self.assertEqual(checkin.pm_proof_text, "I plan to talk to them")
        self.assertEqual(ProofAttempt.objects.filter(checkin=checkin).count(), 0)

    def test_a_successful_resubmission_still_archives_the_refused_try(self):
        """The other half of the one above: the rollback path must not have
        cost the ordinary path its trail row."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Ramesh"})
        checkin = CheckIn.objects.get(goal=goal)
        checkin.pm_proof_text = "I plan to talk to them"
        checkin.coach_reaction = "That's a plan, not a proof."
        checkin.proof_status = CheckIn.ProofStatus.PUSHED_BACK
        checkin.save()

        with mock.patch(
            "coach.views.llm.complete",
            return_value='{"verdict": "accept", "reaction": "ok"}',
        ):
            self.client.post(
                "/api/coach/checkins/prove/", {"text": "Spoke to Ramesh."}
            )
        checkin.refresh_from_db()
        self.assertEqual(checkin.pm_proof_text, "Spoke to Ramesh.")
        archived = ProofAttempt.objects.get(checkin=checkin)
        self.assertEqual(archived.text, "I plan to talk to them")
        self.assertEqual(archived.reaction, "That's a plan, not a proof.")
