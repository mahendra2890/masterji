"""The record a builder can read back or hand to somebody: history, export, the
shared page, the week, the loop report, and the product's own changelog.
"""

import json
import tempfile
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

from .. import (
    export,
    gates,
    prompts,
    views,
    weekly,
)
from ..management.commands import load_changelog, loop_report
from ..models import (
    ChangelogEntry,
    CheckIn,
    Goal,
    GoalRetirement,
    Message,
    Phase,
    PhaseTransition,
    ProofAttempt,
    Workshop,
)
from .base import CoachTestCase, make_user


class SharedRecordTests(CoachTestCase):
    """A closed goal as a page you can hand to somebody.

    Two things are pinned hardest, because this is only the second endpoint in
    the product with no account behind it: what a stranger can read, and what
    they cannot. Everything on the page was computed from rows the builder had
    to earn; nothing they wrote in prose ever leaves through it.
    """

    def close_goal(self, reason="Talked to six people, they won't pay."):
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.accept_proofs(goal, 2)
        self.client.post(f"/api/coach/goals/{goal.id}/retire/", {"reason": reason})
        return GoalRetirement.objects.get(goal=goal)

    def share(self, retirement, on=True):
        url = f"/api/coach/retirements/{retirement.id}/share/"
        return self.client.post(url) if on else self.client.delete(url)

    def test_a_record_is_private_until_the_builder_says_otherwise(self):
        """Off by default, and off for every row that existed before this. A
        record that became public because a feature shipped is not opt-in."""
        retirement = self.close_goal()
        self.assertIsNone(retirement.share_slug)
        self.client.logout()
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/coach/record/anything/").status_code, 404)

    def test_a_stranger_holding_the_link_reads_the_numbers(self):
        retirement = self.close_goal()
        slug = self.share(retirement).json()["share_slug"]

        self.client.force_authenticate(None)
        response = self.client.get(f"/api/coach/record/{slug}/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["title"], "Tiffin app")
        self.assertEqual(body["phase_reached"], Phase.VALIDATION)
        self.assertEqual(body["accepted_proofs"], 2)
        # The verdict, computed by gates.reads_as and never self-reported —
        # which is the whole reason a page like this is worth handing over.
        self.assertEqual(
            body["reads_as"], gates.reads_as(retirement.goal, retirement.outcome)
        )
        self.assertIn("timeline", body)

    def test_the_page_never_carries_a_word_the_builder_wrote(self):
        """The record is the shape of the work, not a diary. Prose is the one
        thing you cannot take back once a link is out."""
        secret = "I only closed it because my father made me."
        retirement = self.close_goal(reason=secret)
        slug = self.share(retirement).json()["share_slug"]

        self.client.force_authenticate(None)
        body = json.dumps(self.client.get(f"/api/coach/record/{slug}/").json())
        self.assertNotIn(secret, body)
        self.assertNotIn("reason", body)
        self.assertNotIn("coach_reaction", body)
        # Nor anything that identifies who they are.
        self.assertNotIn("alice", body)
        self.assertNotIn("user", body)

    def test_turning_it_off_takes_the_link_with_it(self):
        retirement = self.close_goal()
        slug = self.share(retirement).json()["share_slug"]
        self.assertIsNone(self.share(retirement, on=False).json()["share_slug"])

        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/coach/record/{slug}/").status_code, 404)

    def test_turning_it_on_again_is_a_different_link(self):
        """A switch that resurrects the same URL only ever paused it. A link
        handed to somebody and regretted has to be able to stop working."""
        retirement = self.close_goal()
        first = self.share(retirement).json()["share_slug"]
        self.share(retirement, on=False)
        second = self.share(retirement).json()["share_slug"]
        self.assertNotEqual(first, second)

        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/coach/record/{first}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/coach/record/{second}/").status_code, 200)

    def test_the_slug_is_the_access_control_and_is_not_walkable(self):
        """Unguessable rather than sequential: a numeric id would make every
        closed goal in the database walkable by anybody who found one link."""
        retirement = self.close_goal()
        slug = self.share(retirement).json()["share_slug"]
        self.assertNotEqual(slug, str(retirement.id))
        self.assertGreaterEqual(len(slug), 20)
        # Two records in a row do not produce two adjacent slugs, which is the
        # actual property: a sequential one lets anybody who found a link walk
        # to every closed goal in the database.
        second = self.share(self.close_goal()).json()["share_slug"]
        self.assertNotEqual(slug, second)

        self.client.force_authenticate(None)
        # A wrong slug is the same 404 as a missing one: the difference between
        # "no such record" and "that one is private" is itself walkable.
        self.assertEqual(
            self.client.get(f"/api/coach/record/{retirement.id}/").status_code, 404
        )

    def test_only_the_owner_can_share_it(self):
        retirement = self.close_goal()
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.share(retirement).status_code, 404)
        retirement.refresh_from_db()
        self.assertIsNone(retirement.share_slug)


class GoalHistoryTests(CoachTestCase):
    """Reading back a closed idea's full record. Read-only by construction —
    a pk-addressable endpoint is exactly where write access would leak."""

    def test_closed_goal_history_is_readable(self):
        goal = self.make_goal(phase="VALIDATION")
        self.accept_proofs(goal, 2)
        with mock.patch("coach.views.llm.complete", return_value="Noted."):
            self.client.post(f"/api/coach/goals/{goal.pk}/retire/", {"reason": "Dead."})
        response = self.client.get(f"/api/coach/goals/{goal.pk}/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["checkins"]), 2)
        self.assertEqual(response.data["retirement"]["reads_as"], "INVALIDATED")
        self.assertEqual(response.data["goal"]["title"], "Tiffin app")

    def test_active_goal_history_also_works(self):
        goal = self.make_goal()
        self.accept_proofs(goal, 1)
        response = self.client.get(f"/api/coach/goals/{goal.pk}/history/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["retirement"])

    def test_history_is_not_capped_at_the_dashboard_limit(self):
        """CHECKIN_HISTORY is a payload budget for the dashboard, and this view
        is the one that exists because the whole record is too much to send on
        every page load. It used to apply the same 90-row slice, so a goal that
        ran past three months lost its first weeks from the panel that is
        supposed to be the product's memory — and from the export, which reads
        these rows and calls itself the whole story.
        """
        goal = self.make_goal()
        self._days(goal, views.CHECKIN_HISTORY + 5)
        response = self.client.get(f"/api/coach/goals/{goal.pk}/history/")
        self.assertEqual(len(response.data["checkins"]), views.CHECKIN_HISTORY + 5)

    def test_foreign_goal_history_404s(self):
        bobs = self.make_goal(user=self.bob)
        self.assertEqual(
            self.client.get(f"/api/coach/goals/{bobs.pk}/history/").status_code, 404
        )

    def test_history_endpoint_is_read_only(self):
        goal = self.make_goal()
        for method in ("post", "patch", "delete"):
            response = getattr(self.client, method)(
                f"/api/coach/goals/{goal.pk}/history/"
            )
            self.assertEqual(response.status_code, 405, method)

    def test_history_requires_auth(self):
        goal = self.make_goal()
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get(f"/api/coach/goals/{goal.pk}/history/").status_code, 401
        )

    def test_archive_carries_the_goal_id_for_drilling_in(self):
        goal = self.make_goal()
        with mock.patch("coach.views.llm.complete", return_value="Noted."):
            self.client.post(f"/api/coach/goals/{goal.pk}/retire/", {"reason": "Done."})
        archive = self.client.get("/api/coach/state/").data["archive"]
        self.assertEqual(archive[0]["goal"], goal.pk)


class GoalExportTests(CoachTestCase):
    """The record as a file the builder can take with them.

    Every line of it is a rendering of rows that already existed, so most of
    what needs pinning is not the prose: it is that the file carries the whole
    record rather than the dashboard's slice of it, that it carries the refused
    tries as well as the accepted ones, and that it never contains a link which
    is dead by the time anyone opens the file.
    """

    def _export(self, goal) -> str:
        response = self.client.get(f"/api/coach/goals/{goal.pk}/export/")
        self.assertEqual(response.status_code, 200)
        # Asserted on every export below rather than in a test of its own: the
        # client reads the filename out of this header (which is why the API
        # exposes it cross-origin) instead of keeping a second copy of the
        # naming rule, so a header that stopped arriving would rename every
        # download without breaking anything the server can see.
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="{export.filename(goal, date.today())}"',
        )
        return response.content.decode()

    def test_export_carries_the_whole_story(self):
        """Declaration, proof, verdict, the try that was pushed back, the phase
        crossing and the retirement. A record that shows only what was accepted
        is a brochure, and the refusals are the part that makes the rest
        credible — the product's own argument for itself.
        """
        goal = self.make_goal()
        self.accept_proofs(goal, 1)
        self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        goal.refresh_from_db()
        checkin = CheckIn.objects.create(
            goal=goal,
            date=date(2026, 8, 10),
            phase=goal.phase,
            am_declaration="talk to two resellers",
            pm_proof_text="notes from Priya",
            proof_url="https://example.com/notes",
            proof_status=CheckIn.ProofStatus.ACCEPTED,
            coach_reaction="That's the one.",
        )
        ProofAttempt.objects.create(
            checkin=checkin,
            text="I plan to talk to them tomorrow",
            reaction="That's a plan, not a proof.",
        )
        with mock.patch("coach.views.llm.complete", return_value="Noted."):
            self.client.post(
                f"/api/coach/goals/{goal.pk}/retire/", {"reason": "Wrong segment."}
            )

        text = self._export(goal)
        for fragment in (
            "Tiffin app",
            "10 Aug 2026",
            "IDEA → VALIDATION",
            "talk to two resellers",
            "notes from Priya",
            "https://example.com/notes",
            "That's the one.",
            "I plan to talk to them tomorrow",
            "That's a plan, not a proof.",
            "Wrong segment.",
            # Computed at close from contact proofs, never self-declared: one
            # VALIDATION proof is under gates.INVALIDATED_AT, so the honest
            # reading is UNTESTED and the file says so rather than flattering.
            "UNTESTED",
        ):
            self.assertIn(fragment, text, fragment)

    def test_export_is_not_capped_at_the_dashboard_limit(self):
        """The reason this shipped with #88 rather than after it. An export
        built on the dashboard's 90-row query would drop the first weeks of a
        four-month goal while calling itself the full record — the one failure
        this artifact cannot have, because nobody checks a file for the days it
        is missing.
        """
        goal = self.make_goal()
        self._days(goal, views.CHECKIN_HISTORY + 5)
        text = self._export(goal)
        self.assertIn(f"day {views.CHECKIN_HISTORY + 4}", text)

    def test_export_starts_where_the_record_starts(self):
        """A check-in can be dated earlier than the goal row that owns it: dates
        come from the builder's clock and `created_at` from the server's UTC, and
        `streaks.span` exists because of exactly that. The header read
        `created_at` on its own in the first draft of this file, which produced
        "Started 13 Aug" above a first entry dated the 9th — a document that
        argues with itself in front of whoever the builder handed it to.
        """
        goal = self.make_goal()
        earliest = date.today() - timedelta(days=4)
        CheckIn.objects.create(
            goal=goal,
            date=earliest,
            phase=goal.phase,
            am_declaration="the first day of it",
        )
        self.assertIn(
            f"Started: {earliest.day} {earliest:%b %Y}",
            self._export(goal),
        )

    def test_export_names_a_screenshot_and_never_links_it(self):
        """Proof images are signed on read and the links expire in minutes. A
        file kept for a placement interview must not carry one, so the export
        records that a screenshot was filed and stops there. Pinned with storage
        configured, because the failure mode is reusing the serializer payload
        that signs these URLs for the app."""
        goal = self.make_goal()
        CheckIn.objects.create(
            goal=goal,
            date=date(2026, 8, 10),
            phase=goal.phase,
            am_declaration="ship the form",
            pm_proof_text="filed it",
            proof_image_key="proofs/abc.png",
            proof_status=CheckIn.ProofStatus.ACCEPTED,
        )
        with (
            mock.patch("coach.storage.is_configured", return_value=True),
            mock.patch(
                "coach.storage.view_url", return_value="https://r2.example/signed"
            ),
        ):
            text = self._export(goal)
        self.assertIn("screenshot", text.lower())
        self.assertNotIn("https://r2.example/signed", text)

    def test_foreign_goal_export_404s(self):
        bobs = self.make_goal(user=self.bob)
        self.assertEqual(
            self.client.get(f"/api/coach/goals/{bobs.pk}/export/").status_code, 404
        )

    def test_export_requires_auth(self):
        goal = self.make_goal()
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get(f"/api/coach/goals/{goal.pk}/export/").status_code, 401
        )


class ChangelogTests(APITestCase):
    """The product's own record. Public, active-only, newest first — and, as
    the one unscoped table here, it must not leak a way to write to it."""

    def setUp(self):
        # This endpoint is throttled by address, and every request in this file
        # arrives from the same one — so without a clear the counter is shared
        # with whatever ran before, and the class that asserts the refusal would
        # decide whether the classes that don't get one. Same reasoning as
        # CoachTestCase, different key: no user, so it counts by IP.
        cache.clear()
        self.addCleanup(cache.clear)
        ChangelogEntry.all_objects.all().delete()  # the seeded history isn't the subject
        self.old = ChangelogEntry.objects.create(
            shipped_on=date(2026, 8, 5), kind="NEW", title="first build", body="…"
        )
        self.new = ChangelogEntry.objects.create(
            shipped_on=date(2026, 8, 8), kind="FIXED", title="a fix", body="…"
        )

    def test_readable_without_signing_in(self):
        response = self.client.get("/api/coach/changelog/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [e["title"] for e in response.json()["entries"]], ["a fix", "first build"]
        )

    def test_inactive_entries_are_not_served(self):
        self.new.is_active = False
        self.new.save(update_fields=["is_active"])
        response = self.client.get("/api/coach/changelog/")
        self.assertEqual([e["title"] for e in response.json()["entries"]], ["first build"])

    def test_soft_deleted_entries_are_not_served(self):
        self.old.delete()
        response = self.client.get("/api/coach/changelog/")
        self.assertEqual([e["title"] for e in response.json()["entries"]], ["a fix"])

    def test_limit_serves_the_newest_n_and_still_counts_them_all(self):
        """Every screen mounts this to decide one dot, so the mount asks for a
        few. The count has to be of the whole table, not of what was served —
        it is how the client knows there is a tail to go and get."""
        body = self.client.get("/api/coach/changelog/?limit=1").json()
        self.assertEqual([e["title"] for e in body["entries"]], ["a fix"])
        self.assertEqual(body["total"], 2)

    def test_the_total_counts_only_what_would_be_served(self):
        """A total that counted retired or deleted rows would send the client
        after a tail that does not exist, every time it opened the popup."""
        self.new.is_active = False
        self.new.save(update_fields=["is_active"])
        body = self.client.get("/api/coach/changelog/?limit=1").json()
        self.assertEqual(body["total"], 1)
        self.assertEqual([e["title"] for e in body["entries"]], ["first build"])

    def test_a_limit_that_isnt_a_positive_number_is_refused(self):
        """A size the server cannot honour used to fall through to the whole
        table, so the reply to a value nobody could have meant was the largest
        response here — on the one endpoint with no account behind it. It now
        says so instead, in the shape every other refusal in views.py uses."""
        for raw in ["abc", "0", "-3", "2.5", "1e3", "six"]:
            with self.subTest(limit=raw):
                response = self.client.get(f"/api/coach/changelog/?limit={raw}")
                self.assertEqual(response.status_code, 400)
                self.assertIn("positive whole number", response.json()["detail"])

    def test_a_limit_with_no_value_reads_as_no_limit(self):
        """`?limit=` is a proxy or a typed URL dropping the value, not somebody
        asking for a size — and it must keep meaning what leaving it off means,
        because the landing page is where a mangled URL lands."""
        body = self.client.get("/api/coach/changelog/?limit=").json()
        self.assertEqual(len(body["entries"]), 2)
        self.assertEqual(body["total"], 2)

    def test_a_limit_past_the_end_is_not_an_error(self):
        body = self.client.get("/api/coach/changelog/?limit=500").json()
        self.assertEqual(len(body["entries"]), 2)
        self.assertEqual(body["total"], 2)

    def test_same_day_entries_lead_with_the_newest_row(self):
        later = ChangelogEntry.objects.create(
            shipped_on=date(2026, 8, 8), kind="CHANGED", title="also today", body="…"
        )
        response = self.client.get("/api/coach/changelog/")
        titles = [e["title"] for e in response.json()["entries"]]
        self.assertEqual(titles[:2], [later.title, self.new.title])

    def test_the_one_public_endpoint_has_a_ceiling(self):
        """The other three ceilings bound a model bill. This one costs no
        model call — it exists because the only endpoint reachable without an
        account had no ceiling of any kind, and a public surface with none is
        one whose size somebody else decides.

        Patched on the dict the throttle actually consults rather than through
        override_settings — see ThrottleTests for why that does not reach it.
        """
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"changelog": "1/min"}):
            first = self.client.get("/api/coach/changelog/")
            second = self.client.get("/api/coach/changelog/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        # In the product's register, like every other refusal here, not DRF's
        # seconds-remaining arithmetic.
        self.assertNotIn("throttled", second.json()["detail"].lower())

    def test_a_signed_in_mount_does_not_share_the_landing_page_bucket(self):
        """What makes a per-address rate safe to run at all. Every screen in
        the app mounts this component, and a hostel or campus behind one NAT is
        one address — so if signed-in mounts counted there too, a shared
        connection would ration the app shell for everybody on it. DRF keys an
        authenticated request by pk, and the sizing argument in settings rests
        on that being true.
        """
        alice, bob = make_user("alice"), make_user("bob")
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"changelog": "1/min"}):
            self.client.force_authenticate(alice)
            self.assertEqual(self.client.get("/api/coach/changelog/").status_code, 200)
            self.assertEqual(self.client.get("/api/coach/changelog/").status_code, 429)
            # A different account at the same address, already over the limit
            # the anonymous bucket would have applied.
            self.client.force_authenticate(bob)
            self.assertEqual(self.client.get("/api/coach/changelog/").status_code, 200)
        self.client.force_authenticate(None)

    def test_endpoint_is_read_only(self):
        response = self.client.post(
            "/api/coach/changelog/", {"shipped_on": "2026-08-09", "title": "mine"}
        )
        self.assertEqual(response.status_code, 405)
        self.assertEqual(ChangelogEntry.objects.count(), 2)

    def test_seeded_history_ships_with_the_database(self):
        """The migration's entries are the product's record — a fresh database
        has them without anyone typing into the admin."""
        from django.db.migrations.loader import MigrationLoader

        self.assertIn(
            ("coach", "0011_seed_changelog"), MigrationLoader(None).graph.nodes
        )


class SeededChangelogTests(TestCase):
    """The rows the migrations put in every database, read the way the frontend
    reads them.

    Separate from ChangelogTests because that class deletes the seeded history in
    setUp — how the endpoint behaves is not about its content — and this is the
    one assertion that is only about the content.
    """

    def test_every_seeded_kind_is_one_the_frontend_can_render(self):
        """`kind` has `choices`, and choices are not enforced on write: a data
        migration calling `get_or_create` never reaches `full_clean`, so a typo
        ships. One did — 0058 seeded the TRACTION announcement as "ADDED" —
        and components/Changelog.tsx looks the label up in a total map, so
        `KIND_LABEL[e.kind]` came back `undefined` and the newest capability the
        product had shipped wore a chip with no text and no styling.

        Asserted over the rows rather than by parsing the migration files,
        because the rows are what the frontend gets. Guards every future row for
        the price of this one.
        """
        kinds = set(ChangelogEntry.all_objects.values_list("kind", flat=True))
        # Without this the assertion below passes on an empty table, which is
        # the one way it could go quiet without going green for a good reason.
        self.assertTrue(kinds)
        self.assertEqual(kinds - set(ChangelogEntry.Kind.values), set())


# --- changelog entries as files, not migrations ------------------------------


ENTRY = """---
shipped_on: 2026-08-14
kind: CHANGED
title: The coach knows how long it has been
---

Masterji could see your phase, your count and your streak, and not one
date. He now gets two facts.
"""


def write(directory, name, text):
    (Path(directory) / name).write_text(text, encoding="utf-8")


class ChangelogFileTests(TestCase):
    """`load_changelog`: the reason `check_migration_leaf` keeps firing, removed.

    57 of `coach`'s 74 migrations were changelog data seeds, and the house rule
    that every builder-visible change ships a row in the same pull request meant
    every substantive pull request wrote a migration. Two parallel sessions
    therefore collided on the leaf essentially every time. Entries are files
    now, one per entry, so two sessions write two different files and there is
    nothing to collide on.
    """

    def setUp(self):
        # The 57 rows the migrations seeded are not the subject here, and they
        # would turn every count below into a count of history plus one. Same
        # reasoning, and the same line, as ChangelogTests.
        ChangelogEntry.all_objects.all().delete()

    def load(self, directory):
        out = StringIO()
        call_command("load_changelog", dir=str(directory), stdout=out)
        return out.getvalue()

    def test_a_file_becomes_a_row(self):
        """The whole point, and the fields a reader actually gets."""
        with tempfile.TemporaryDirectory() as d:
            write(d, "2026-08-14-how-long.md", ENTRY)
            self.load(d)
        row = ChangelogEntry.all_objects.get(title="The coach knows how long it has been")
        self.assertEqual(row.shipped_on, date(2026, 8, 14))
        self.assertEqual(row.kind, "CHANGED")
        self.assertTrue(row.is_active)

    def test_the_body_arrives_as_one_paragraph(self):
        """`components/Changelog.tsx` renders the body as a single `<p>`, so
        the file's wrapping has nowhere to land. Unwrapping on load rather than
        at the renderer keeps the row identical in shape to the 57 the
        migrations wrote, so the two sources cannot drift."""
        with tempfile.TemporaryDirectory() as d:
            write(d, "2026-08-14-how-long.md", ENTRY)
            self.load(d)
        body = ChangelogEntry.all_objects.get(shipped_on=date(2026, 8, 14)).body
        self.assertNotIn("\n", body)
        self.assertIn("not one date. He now gets two facts.", body)

    def test_loading_twice_makes_one_row(self):
        """Every boot runs this. If it were not idempotent, `start.sh` would
        duplicate the entire changelog on every deploy."""
        with tempfile.TemporaryDirectory() as d:
            write(d, "2026-08-14-how-long.md", ENTRY)
            self.load(d)
            self.load(d)
        self.assertEqual(
            ChangelogEntry.all_objects.filter(shipped_on=date(2026, 8, 14)).count(), 1
        )

    def test_an_entry_edited_in_the_admin_survives_the_next_deploy(self):
        """`get_or_create`, never update — and that is a product decision, not
        an implementation detail. The README says the changelog is written from
        the admin; the file is where a row is born, and fixing a typo in
        something already published stays an admin job."""
        with tempfile.TemporaryDirectory() as d:
            write(d, "2026-08-14-how-long.md", ENTRY)
            self.load(d)
            row = ChangelogEntry.all_objects.get(shipped_on=date(2026, 8, 14))
            row.body = "Corrected in the admin."
            row.save()
            self.load(d)
        row.refresh_from_db()
        self.assertEqual(row.body, "Corrected in the admin.")

    def test_a_retired_entry_does_not_come_back_on_the_next_boot(self):
        """Soft delete is how an entry is retired without losing its text. If
        the loader read `objects` instead of `all_objects` it would not see the
        retired row, would create a second one, and retiring anything would
        last until the next deploy."""
        with tempfile.TemporaryDirectory() as d:
            write(d, "2026-08-14-how-long.md", ENTRY)
            self.load(d)
            ChangelogEntry.all_objects.get(shipped_on=date(2026, 8, 14)).delete()
            self.load(d)
        self.assertEqual(
            ChangelogEntry.all_objects.filter(shipped_on=date(2026, 8, 14)).count(), 1
        )
        self.assertEqual(
            ChangelogEntry.objects.filter(shipped_on=date(2026, 8, 14)).count(), 0
        )

    def test_the_readme_in_the_directory_is_not_an_entry(self):
        """The date prefix on entry filenames is what keeps the directory's own
        documentation out of the glob, which is why it is a convention the
        loader depends on rather than decoration."""
        with tempfile.TemporaryDirectory() as d:
            write(d, "README.md", "# Changelog entries\n\nNot an entry.\n")
            write(d, "2026-08-14-how-long.md", ENTRY)
            self.load(d)
        self.assertEqual(ChangelogEntry.all_objects.count(), 1)

    def test_within_a_day_the_files_read_in_filename_order(self):
        """`ChangelogEntry` breaks a same-day tie on `-id`, so insertion order
        is the order a reader sees. Sorting the glob is what makes that
        predictable instead of filesystem-dependent."""
        with tempfile.TemporaryDirectory() as d:
            write(d, "2026-08-14-a-first.md", ENTRY.replace("The coach knows how long it has been", "First"))
            write(d, "2026-08-14-b-second.md", ENTRY.replace("The coach knows how long it has been", "Second"))
            self.load(d)
        titles = list(
            ChangelogEntry.objects.filter(shipped_on=date(2026, 8, 14)).values_list(
                "title", flat=True
            )
        )
        # Model ordering is ("-shipped_on", "-id"): newest first within the day.
        self.assertEqual(titles, ["Second", "First"])

    def test_a_kind_the_frontend_cannot_render_is_refused(self):
        """`choices` are not enforced on write — `get_or_create` never reaches
        `full_clean` — so a typo ships. One did: 0058 seeded a row as "ADDED"
        and `KIND_LABEL[e.kind]` came back `undefined`, so the newest thing the
        product had shipped wore a chip with no text. Checked here because this
        is now the only door new rows come through."""
        with self.assertRaises(CommandError) as caught:
            load_changelog.parse_entry(ENTRY.replace("CHANGED", "ADDED"), "x.md")
        self.assertIn("ADDED", str(caught.exception))

    def test_every_malformed_shape_names_the_file(self):
        """A boot-time loader that says "invalid entry" and stops is a worse
        deploy than one that says which file. The name is in every message."""
        for label, text in (
            ("no header", "shipped_on: 2026-08-14\n\nBody.\n"),
            ("unclosed header", "---\nshipped_on: 2026-08-14\nkind: NEW\n"),
            ("missing title", ENTRY.replace("title: The coach knows how long it has been\n", "")),
            ("not a date", ENTRY.replace("2026-08-14", "the fourteenth")),
            ("empty body", "---\nshipped_on: 2026-08-14\nkind: NEW\ntitle: T\n---\n\n"),
            ("long title", ENTRY.replace("The coach knows how long it has been", "T" * 121)),
            ("bad is_active", ENTRY.replace("kind: CHANGED", "kind: CHANGED\nis_active: maybe")),
        ):
            with self.subTest(label):
                with self.assertRaises(CommandError) as caught:
                    load_changelog.parse_entry(text, "2026-08-14-how-long.md")
                self.assertIn("2026-08-14-how-long.md", str(caught.exception))

    def test_an_empty_directory_is_not_an_error(self):
        """A fresh checkout has no entries here yet, and a boot is not the
        place to have an opinion about that."""
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("0 new", self.load(d))

    def test_every_entry_in_the_tree_parses(self):
        """The ratchet. Guards every entry a future session writes for the
        price of this one, and fails in CI rather than at boot — which is the
        whole reason `start.sh` can afford to run the loader with `|| true`."""
        load_changelog.read_entries(load_changelog.ENTRIES_DIR)


# --- counting whether the loop works -----------------------------------------


class LoopReportTests(CoachTestCase):
    """The readout that decides which other work matters.

    Nothing in the repo counted whether the product does what it claims, so the
    backlog was being ranked on argument. What is pinned here is the arithmetic
    that is not a plain COUNT — the two places a readout like this quietly
    starts lying — plus the fact that it never writes.
    """

    def report(self):
        out = StringIO()
        call_command("loop_report", stdout=out)
        return out.getvalue()

    def test_it_runs_on_an_empty_database(self):
        """Every rate here has a denominator that starts at zero, and a report
        that divides by it on a fresh deploy is a report nobody runs twice."""
        Goal.objects.all().delete()
        self.assertIn("The workshop", self.report())

    def test_a_spent_workshop_is_the_conversion(self):
        """`GoalsView.post` flips every open workshop to SPENT at the moment a
        goal is committed, so SPENT *is* "ended in a committed goal" — nothing
        has to be inferred and no join is needed. If that ever stops being true
        this number silently becomes something else."""
        Workshop.objects.create(user=self.alice, status=Workshop.Status.SPENT)
        Workshop.objects.create(user=self.bob, status=Workshop.Status.OPEN)
        text = self.report()
        self.assertIn("opened                                       2", text)
        self.assertIn("ended in a committed goal                    1  (50%)", text)

    def test_time_in_a_phase_is_measured_from_entering_it(self):
        """IDEA is entered when the goal is created — there is no transition
        into the first rung — and every later phase when the transition into it
        was written. Reading `Goal.phase_entered_at` instead would only ever
        describe the phase a goal is in now."""
        goal = self.make_goal()
        Goal.objects.filter(pk=goal.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        row = PhaseTransition.objects.create(
            goal=goal, from_phase=Phase.IDEA, to_phase=Phase.VALIDATION
        )
        PhaseTransition.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(days=4)
        )
        durations = loop_report.phase_durations()
        self.assertAlmostEqual(durations[Phase.IDEA][0], 6.0, places=1)

    def test_an_unfinished_phase_is_not_counted_as_a_fast_one(self):
        """A goal still sitting in BUILD has not cleared BUILD. Counting it
        would make the median fall every time somebody new arrived, which is
        the one way this number could move in the opposite direction to the
        thing it describes."""
        self.make_goal(phase=Phase.BUILD)
        self.assertEqual(loop_report.phase_durations().get(Phase.BUILD, []), [])

    def test_retention_only_counts_builders_who_had_the_chance(self):
        """The denominator is the whole honesty of a retention number. A
        builder who signed up yesterday has not failed to come back on day 30,
        and counting them would drag every window down with each new signup."""
        today = timezone.localdate()
        yesterday = {self.alice.id: today - timedelta(days=1)}
        rows = dict(
            (window, (back, eligible))
            for window, back, eligible in loop_report.return_windows(
                yesterday, {self.alice.id: {today - timedelta(days=1)}}
            )
        )
        self.assertEqual(rows[2], (0, 1))  # day 2 has arrived; they did not return
        self.assertEqual(rows[7], (0, 0))  # day 7 has not arrived — not a failure
        self.assertEqual(rows[30], (0, 0))

    def test_a_refused_evening_that_was_answered_counts_as_answered(self):
        """The question the product's whole argument rests on: does a refusal
        send a builder back to the work, or out of the door? An archived
        attempt means it was refused at least once; the status now is what they
        did about it."""
        goal = self.make_goal()
        won = CheckIn.objects.create(
            goal=goal, date=date.today(), phase=goal.phase,
            am_declaration="x", pm_proof_text="second try",
            proof_status=CheckIn.ProofStatus.ACCEPTED,
        )
        ProofAttempt.objects.create(checkin=won, text="first try", reaction="no")
        lost = CheckIn.objects.create(
            goal=goal, date=date.today() - timedelta(days=1), phase=goal.phase,
            am_declaration="x", pm_proof_text="still not",
            proof_status=CheckIn.ProofStatus.PUSHED_BACK,
        )
        ProofAttempt.objects.create(checkin=lost, text="first try", reaction="no")
        text = self.report()
        self.assertIn("evenings refused at least once               2", text)
        self.assertIn("…later accepted                              1  (50%)", text)

    def test_the_readout_writes_nothing(self):
        """It reuses `gates.py` and `streaks.py`, which is what makes it safe:
        the same arithmetic that refuses a phase advance, adding no authority
        and able to contradict nothing. A readout that wrote would be a second
        opinion about the record."""
        goal = self.make_goal()
        self.accept_proofs(goal, 1)
        before = {
            model.__name__: model.all_objects.count()
            for model in (Goal, CheckIn, PhaseTransition, Workshop, ProofAttempt)
        }
        self.report()
        after = {
            model.__name__: model.all_objects.count()
            for model in (Goal, CheckIn, PhaseTransition, Workshop, ProofAttempt)
        }
        self.assertEqual(before, after)
        goal.refresh_from_db()
        self.assertEqual(goal.phase, Phase.IDEA)


class WeeklyDigestTests(CoachTestCase):
    """The week read back on the first visit of a new week.

    Every number here comes from rows the builder already filed — the digest
    asks for nothing, which is the property the feature is built on. What is
    pinned is the window, the once-a-week write, and the two weeks that must
    not read the same: one where nothing was declared, and one where days were
    complete and the gate still did not move.
    """

    # A real Monday and the Sunday that closes its week. Fixed dates are safe
    # for the pure functions, which take the window as an argument; the view
    # tests below have to work in dates _client_day will accept, which is
    # within a day of the server's.
    MONDAY = date(2026, 8, 10)
    SUNDAY = date(2026, 8, 16)

    def day(self, goal, on, *, declared=True, proved=True, accepted=False, subject=""):
        return CheckIn.objects.create(
            goal=goal,
            date=on,
            phase=goal.phase,
            am_declaration="ship the form" if declared else "",
            pm_proof_text="shipped it" if proved else "",
            subject=subject,
            proof_status=CheckIn.ProofStatus.ACCEPTED
            if accepted
            else CheckIn.ProofStatus.NONE,
        )

    def last_week(self, today=None):
        """The window the digest covers on a visit made today."""
        today = today or date.today()
        return weekly.week_start(today) - timedelta(days=7)

    def test_the_week_is_monday_to_sunday_on_the_builders_own_calendar(self):
        """`CheckIn.date` is the client's local date and every other timestamp
        on these rows is server UTC, so the window has to be measured against
        the dates the builder filed under. Sunday is the day this gets tested:
        it closes the week it is in and must not be read into the next one,
        which is where the digest would silently drop a builder's best day."""
        goal = self.make_goal()
        self.day(goal, self.SUNDAY)
        self.assertEqual(weekly.week_start(self.SUNDAY), self.MONDAY)
        self.assertEqual(weekly.week_start(self.MONDAY), self.MONDAY)
        self.assertEqual(weekly.summary(goal, self.MONDAY)["days"], 1)
        self.assertEqual(
            weekly.summary(goal, self.MONDAY + timedelta(days=7))["days"], 0
        )

    def test_a_day_counts_only_when_it_was_declared_and_proved(self):
        """The same rule `streaks.py` counts a run by. A digest that counted
        declarations would tell a builder who declared seven mornings and
        proved none that they had a complete week."""
        goal = self.make_goal()
        self.day(goal, self.MONDAY)
        self.day(goal, self.MONDAY + timedelta(days=1), proved=False)
        self.day(goal, self.MONDAY + timedelta(days=2), declared=False)
        summary = weekly.summary(goal, self.MONDAY)
        self.assertEqual(summary["days"], 1)
        self.assertEqual(summary["filed"], 3)

    def test_three_evenings_about_one_person_is_one_person(self):
        """The rule `gates.accepted_proofs` already enforces at VALIDATION —
        "the person already counted cannot be counted again". A digest that
        counted rows would hand back a bigger number than the gate will, in
        the week the builder is deciding whether the gate is fair."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        for i in range(3):
            self.day(
                goal,
                self.MONDAY + timedelta(days=i),
                accepted=True,
                subject="Ravi",
            )
        summary = weekly.summary(goal, self.MONDAY)
        self.assertEqual(summary["accepted"], 3)
        self.assertEqual(summary["people"], 1)

    def test_the_digest_is_written_once_a_week_not_once_a_load(self):
        """The trigger is lazy — there is no scheduler on this deployment — so
        the row itself has to be claimed. The dashboard refetches after every
        turn, so "first request of a new week" is a race unless the claim is
        one atomic write."""
        goal = self.make_goal()
        self.day(goal, self.last_week())
        for _ in range(3):
            self.client.get("/api/coach/state/")
        digests = goal.messages.filter(role=Message.Role.SYSTEM)
        self.assertEqual(digests.count(), 1)
        # The half the client reads: SYSTEM now carries two different things,
        # and only one of them has a turn worth offering to send again.
        self.assertEqual(digests.get().kind, Message.Kind.DIGEST)
        goal.refresh_from_db()
        self.assertEqual(goal.last_digest_week, self.last_week())

    def test_a_week_of_work_that_moved_the_gate_by_zero_still_reads_back(self):
        """The builder this feature exists for. Seven honest days that banked
        nothing is invisible at daily grain and is the whole of what weekly
        grain is for, so the digest has to state the zero rather than quietly
        report the days and let the number look like progress."""
        goal = self.make_goal()
        for i in range(3):
            self.day(goal, self.last_week() + timedelta(days=i))
        self.client.get("/api/coach/state/")
        digest = goal.messages.get(role=Message.Role.SYSTEM).content
        self.assertIn("3 of 7 days complete", digest)
        self.assertIn("nothing accepted", digest)

    def test_a_week_with_nothing_declared_writes_nothing(self):
        """A goal committed on Sunday must not be handed a report card on
        Monday saying it did nothing last week, and a builder coming back
        after a month must not walk into a wall of empty weeks. No rows in the
        window means there is no week to read back — but the marker still
        moves, so this is asked once and not on every load."""
        goal = self.make_goal()
        self.client.get("/api/coach/state/")
        self.assertFalse(goal.messages.filter(role=Message.Role.SYSTEM).exists())
        goal.refresh_from_db()
        self.assertEqual(goal.last_digest_week, self.last_week())

    def test_last_weeks_facts_reach_the_prompt(self):
        """The cheaper half of the value: Monday's conversation opens knowing
        what the week held, rather than the coach reading it off a transcript
        it has to interpret. Absent by default, like the calendar block — a
        caller with no week measured gets the prompt it always got."""
        goal = self.make_goal()
        self.assertEqual(prompts.week_block(None), "")
        block = prompts.week_block(
            {"days": 4, "accepted": 2, "people": 2, "advanced_to": "", "filed": 5}
        )
        self.assertIn("4 of 7 days complete", block)
        self.assertIn("2 accepted", block)

    def test_the_week_they_worked_is_the_one_read_back_after_a_gap(self):
        """The builder this used to do nothing for. Six days and two proofs,
        two weeks away, then a return — and the window their visit lands after
        is empty, so the old rule wrote nothing and moved the marker past the
        week they were proud of, permanently. It now reads back the last week
        that had check-ins in it, and names the date: the same counts under
        "Last week" would tell somebody just back from exams that they had
        worked six days while they were gone."""
        goal = self.make_goal()
        worked = self.last_week() - timedelta(days=14)
        for i in range(6):
            self.day(goal, worked + timedelta(days=i), accepted=i < 2, subject=f"p{i}")
        for _ in range(3):
            self.client.get("/api/coach/state/")
        digests = goal.messages.filter(role=Message.Role.SYSTEM)
        # One message, not one per missed week — the shape #185 rejected.
        self.assertEqual(digests.count(), 1)
        said = digests.get().content
        self.assertIn(f"Picking up from the week of {worked.day} {worked:%b}", said)
        self.assertIn("6 of 7 days complete", said)
        self.assertIn("2 accepted", said)
        self.assertNotIn("Last week", said)
        # And the marker still moves to the window the visit is in, so this
        # stays once a week rather than once per week missed.
        goal.refresh_from_db()
        self.assertEqual(goal.last_digest_week, self.last_week())

    def test_a_week_already_read_back_is_not_read_back_again(self):
        """Why the search floor is the marker and not the calendar. This
        builder read the digest about the week they worked and then vanished;
        with no floor the search would reach back past their own marker and
        hand them that same week a second time, weeks later, as news."""
        goal = self.make_goal()
        worked = self.last_week() - timedelta(days=14)
        for i in range(6):
            self.day(goal, worked + timedelta(days=i))
        Goal.objects.filter(pk=goal.pk).update(last_digest_week=worked)
        self.client.get("/api/coach/state/")
        self.assertFalse(goal.messages.filter(role=Message.Role.SYSTEM).exists())
        goal.refresh_from_db()
        self.assertEqual(goal.last_digest_week, self.last_week())

    def test_a_week_older_than_the_look_back_is_left_where_it_is(self):
        """`LOOK_BACK_WEEKS` is a claim about the copy rather than a cost
        bound — the query is one indexed read either way. "Picking up from"
        stops being true once the builder is starting again instead of
        continuing, and past that line the absence belongs to the coach, who
        already has it through `days_since_complete`."""
        goal = self.make_goal()
        stale = self.last_week() - timedelta(days=7 * weekly.LOOK_BACK_WEEKS)
        for i in range(6):
            self.day(goal, stale + timedelta(days=i))
        self.client.get("/api/coach/state/")
        self.assertFalse(goal.messages.filter(role=Message.Role.SYSTEM).exists())

    def test_the_named_week_is_said_in_both_tones(self):
        """Owed in Hinglish for the reason STOCK_OFFER_ACCEPT is: this is on
        the happy path and it recurs, so an English-only clause would meet a
        builder who asked for Hinglish on the one morning they came back."""
        summary = {"filed": 6, "days": 6, "accepted": 2, "people": 0, "advanced_to": ""}
        week_of = date(2026, 8, 3)
        self.assertIn(
            "Picking up from the week of 3 Aug",
            weekly.digest(summary, "ENGLISH", week_of),
        )
        self.assertIn(
            "3 Aug wale hafte se", weekly.digest(summary, "HINGLISH", week_of)
        )
        # The ordinary week is still the ordinary sentence, and still undated.
        self.assertIn("Last week", weekly.digest(summary, "ENGLISH"))
        self.assertIn("Pichhle hafte", weekly.digest(summary, "HINGLISH"))

    def test_the_prompt_names_the_week_it_was_handed(self):
        """The digest is a SYSTEM row and SYSTEM rows are excluded from the
        transcript, so the coach never sees the message the builder just read.
        A block still saying "Last week" over an older window would be a false
        line in the one block the prompt tells the model to trust over
        anything said in chat."""
        summary = {"days": 6, "accepted": 2, "people": 0, "advanced_to": "", "filed": 6}
        self.assertIn("- Last week:", prompts.week_block(summary))
        self.assertIn("- Week of 3 Aug:", prompts.week_block(summary, date(2026, 8, 3)))
