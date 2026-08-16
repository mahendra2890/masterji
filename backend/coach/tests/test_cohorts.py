"""`cohorts.py` — a lens over the record, with no way to write on it."""

import json
from datetime import date, timedelta

from .. import (
    cohorts,
    gates,
    streaks,
    views,
)
from ..models import (
    JOIN_CODE_ALPHABET,
    CheckIn,
    Cohort,
    CohortMember,
    Goal,
    Phase,
)
from .base import CoachTestCase, make_user

# --- the cohort: a lens over the record, with no way to write on it ----------


class CohortTestCase(CoachTestCase):
    """Fixtures for a cohort, in the shape the board actually reads.

    `accept_proofs` on the base case banks into the goal's CURRENT phase, which
    is what the gate counts. The board counts something wider —
    `accepted_proofs_total` is every accepted proof whatever phase stamped it,
    and `contact_proofs` is the VALIDATION-onward subset — so these helpers
    stamp phases explicitly rather than going through the gate.
    """

    def make_cohort(self, name="Delta E-Cell", **kwargs) -> Cohort:
        return Cohort.objects.create(name=name, **kwargs)

    def join(self, cohort: Cohort, user) -> CohortMember:
        return CohortMember.objects.create(cohort=cohort, user=user)

    def bank(self, goal: Goal, phase, n: int, accepted=True):
        """n proofs stamped with `phase`, whatever phase the goal is in now."""
        for i in range(n):
            CheckIn.objects.create(
                goal=goal,
                date=date.today() - timedelta(days=i),
                phase=phase,
                am_declaration="talk to a customer",
                pm_proof_text="notes from the talk",
                proof_status=(
                    CheckIn.ProofStatus.ACCEPTED
                    if accepted
                    else CheckIn.ProofStatus.PUSHED_BACK
                ),
            )

    def complete_days(self, goal: Goal, days: list[int]):
        """A complete day (declared AND proved) that many days before today."""
        for offset in days:
            CheckIn.objects.create(
                goal=goal,
                date=date.today() - timedelta(days=offset),
                phase=goal.phase,
                am_declaration="did the thing",
                pm_proof_text="here it is",
            )


class CohortConsentTests(CohortTestCase):
    """Joining by code IS the consent, so a builder who has not joined is
    invisible to every cohort surface — not listed, not ranked, not counted."""

    def test_a_builder_who_has_not_joined_sees_no_cohorts(self):
        self.make_cohort()
        response = self.client.get("/api/coach/cohorts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cohorts"], [])

    def test_a_non_member_cannot_read_a_cohort_by_id(self):
        """A 404 rather than a 403: the difference between "no such cohort" and
        "not yours" is itself something a stranger can walk to learn which
        cohorts exist."""
        cohort = self.make_cohort()
        self.join(cohort, self.bob)
        response = self.client.get(f"/api/coach/cohorts/{cohort.id}/")
        self.assertEqual(response.status_code, 404)

    def test_a_cohort_that_does_not_exist_refuses_identically(self):
        cohort = self.make_cohort()
        self.join(cohort, self.bob)
        mine = self.client.get(f"/api/coach/cohorts/{cohort.id}/")
        missing = self.client.get("/api/coach/cohorts/9999/")
        self.assertEqual(mine.status_code, missing.status_code)
        self.assertEqual(mine.json(), missing.json())

    def test_a_member_of_one_cohort_cannot_read_another(self):
        """The tenancy line this feature turns on. Alice is a real member of a
        real cohort, which is exactly the caller a check at the edge of the
        response would let through."""
        mine = self.make_cohort("Mine")
        theirs = self.make_cohort("Theirs")
        self.join(mine, self.alice)
        self.join(theirs, self.bob)
        self.assertEqual(
            self.client.get(f"/api/coach/cohorts/{mine.id}/").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/api/coach/cohorts/{theirs.id}/").status_code, 404
        )

    def test_a_builder_who_has_not_joined_is_not_counted_in_anyones_aggregate(self):
        """Not on the board, and not in its size either — invisible means
        invisible, including as an anonymous +1."""
        cohort = self.make_cohort()
        self.join(cohort, self.alice)
        outsider = make_user("carol")
        self.bank(self.make_goal(user=outsider), Phase.VALIDATION, 5)

        body = self.client.get(f"/api/coach/cohorts/{cohort.id}/").json()
        self.assertEqual(body["cohort"]["members"], 1)
        self.assertEqual([row["name"] for row in body["board"]], ["alice"])

    def test_leaving_removes_the_row_and_touches_nothing_the_builder_earned(self):
        cohort = self.make_cohort()
        self.join(cohort, self.alice)
        goal = self.make_goal()
        self.bank(goal, Phase.VALIDATION, 3)
        before = gates.accepted_proofs_total(goal)

        response = self.client.delete(f"/api/coach/cohorts/{cohort.id}/membership/")
        self.assertEqual(response.status_code, 204)

        # Gone from the board…
        self.assertEqual(self.client.get("/api/coach/cohorts/").json()["cohorts"], [])
        self.assertEqual(
            self.client.get(f"/api/coach/cohorts/{cohort.id}/").status_code, 404
        )
        # …and their own record is identical.
        goal.refresh_from_db()
        self.assertEqual(gates.accepted_proofs_total(goal), before)
        self.assertEqual(Goal.objects.filter(user=self.alice).count(), 1)
        self.assertEqual(CheckIn.objects.filter(goal=goal).count(), 3)

    def test_a_member_who_left_is_not_counted_in_the_boards_size(self):
        """The soft-delete trap this feature is most exposed to.
        `SoftDeleteManager` puts its predicate on the model being queried and
        never on a reverse join, so a size that forgot the filter would keep
        counting everybody who ever left."""
        cohort = self.make_cohort()
        self.join(cohort, self.alice)
        leaver = self.join(cohort, self.bob)
        leaver.delete()  # soft

        body = self.client.get(f"/api/coach/cohorts/{cohort.id}/").json()
        self.assertEqual(body["cohort"]["members"], 1)
        self.assertEqual([row["name"] for row in body["board"]], ["alice"])

    def test_deleting_the_account_leaves_every_cohort(self):
        """Free, and only because `accounts.erasure._descend` walks the model
        graph rather than a hand-written list of models. Pinned here because
        the day somebody replaces that walk with a list, this is what breaks
        and nothing else would say so."""
        from accounts import erasure

        cohort = self.make_cohort()
        self.join(cohort, self.alice)
        self.join(cohort, self.bob)

        erasure.erase(self.bob)

        self.assertEqual(CohortMember.objects.filter(cohort=cohort).count(), 1)
        body = self.client.get(f"/api/coach/cohorts/{cohort.id}/").json()
        self.assertEqual(body["cohort"]["members"], 1)
        self.assertEqual([row["name"] for row in body["board"]], ["alice"])


class CohortJoinCodeTests(CohortTestCase):
    """How a code is issued, what it is not, and what rotating one does."""

    def test_joining_by_code_is_what_puts_a_builder_on_the_board(self):
        cohort = self.make_cohort()
        response = self.client.post(
            "/api/coach/cohorts/join/", {"code": cohort.join_code}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["cohort"]["id"], cohort.id)
        self.assertEqual(
            [c["id"] for c in self.client.get("/api/coach/cohorts/").json()["cohorts"]],
            [cohort.id],
        )

    def test_a_code_is_read_however_it_was_typed(self):
        """It is read off a slide and typed on a phone. A join that failed on a
        space would be indistinguishable from a wrong code."""
        cohort = self.make_cohort()
        typed = f"  {cohort.join_code[:4].lower()}-{cohort.join_code[4:].lower()} "
        response = self.client.post("/api/coach/cohorts/join/", {"code": typed})
        self.assertEqual(response.status_code, 201)

    def test_a_minted_code_avoids_the_characters_that_get_misread(self):
        """O/0 and I/1/L off a projector are the same character, and forty
        people typing it is forty chances to be wrong about that."""
        codes = "".join(self.make_cohort(f"E-Cell {i}").join_code for i in range(40))
        self.assertEqual(set(codes) - set(JOIN_CODE_ALPHABET), set())
        for lookalike in "O0I1L":
            self.assertNotIn(lookalike, codes)

    def test_joining_twice_is_the_same_membership(self):
        cohort = self.make_cohort()
        for _ in range(3):
            self.client.post("/api/coach/cohorts/join/", {"code": cohort.join_code})
        self.assertEqual(CohortMember.objects.filter(cohort=cohort).count(), 1)
        body = self.client.get(f"/api/coach/cohorts/{cohort.id}/").json()
        self.assertEqual(len(body["board"]), 1)

    def test_a_wrong_code_is_the_same_refusal_as_a_rotated_one(self):
        """Rotation is how a cohort is closed to new joins, so from outside the
        two are the same event and must not be told apart."""
        cohort = self.make_cohort()
        stale = cohort.join_code
        cohort.join_code = "NEWCODE9"
        cohort.save(update_fields=["join_code"])

        rotated = self.client.post("/api/coach/cohorts/join/", {"code": stale})
        nonsense = self.client.post("/api/coach/cohorts/join/", {"code": "ZZZZZZZZ"})
        self.assertEqual(rotated.status_code, 404)
        self.assertEqual(rotated.json(), nonsense.json())

    def test_rotating_a_code_never_ejects_a_member(self):
        """A code is an invitation, not a session. A rotation that ejected
        forty people would make the safe operation the dangerous one."""
        cohort = self.make_cohort()
        self.join(cohort, self.alice)
        cohort.join_code = "ROTATED2"
        cohort.save(update_fields=["join_code"])

        response = self.client.get(f"/api/coach/cohorts/{cohort.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cohort"]["members"], 1)

    def test_leaving_and_rejoining_works(self):
        """The unique constraint is conditional on the soft-delete predicate,
        so the tombstone does not occupy the slot."""
        cohort = self.make_cohort()
        self.client.post("/api/coach/cohorts/join/", {"code": cohort.join_code})
        self.client.delete(f"/api/coach/cohorts/{cohort.id}/membership/")
        again = self.client.post("/api/coach/cohorts/join/", {"code": cohort.join_code})
        self.assertEqual(again.status_code, 201)
        self.assertEqual(CohortMember.objects.filter(cohort=cohort).count(), 1)

    def test_an_empty_code_is_asked_for_rather_than_hunted_for(self):
        response = self.client.post("/api/coach/cohorts/join/", {"code": "   "})
        self.assertEqual(response.status_code, 400)

    def test_a_megabyte_in_the_code_field_is_a_miss_not_a_query(self):
        response = self.client.post("/api/coach/cohorts/join/", {"code": "A" * 5000})
        self.assertEqual(response.status_code, 404)

    def test_there_is_no_expiry_field_to_forget_to_set(self):
        """Written as a test because the simple version is a decision somebody
        will later be tempted to "fix" — see the issue thread. A deadline
        nobody set is a support ticket in three months."""
        fields = {f.name for f in Cohort._meta.get_fields()}
        self.assertNotIn("expires_at", fields)
        self.assertNotIn("is_open", fields)


class CohortReadOnlyTests(CohortTestCase):
    """No coordinator can bank or unbank anything. The board has no write
    path at all — not an unused one, none."""

    WRITES = ["post", "put", "patch", "delete"]

    def setUp(self):
        super().setUp()
        self.cohort = self.make_cohort()
        self.join(self.cohort, self.alice)
        self.join(self.cohort, self.bob)
        self.goal = self.make_goal(user=self.bob)
        self.bank(self.goal, Phase.VALIDATION, 2)

    def test_the_board_answers_no_verb_but_get(self):
        url = f"/api/coach/cohorts/{self.cohort.id}/"
        for verb in self.WRITES:
            with self.subTest(verb=verb):
                response = getattr(self.client, verb)(url, {})
                self.assertEqual(response.status_code, 405)

    def test_the_listing_answers_no_verb_but_get(self):
        for verb in self.WRITES:
            with self.subTest(verb=verb):
                response = getattr(self.client, verb)("/api/coach/cohorts/", {})
                self.assertEqual(response.status_code, 405)

    def test_the_board_view_defines_no_write_handler_at_all(self):
        """Asserted on the class, not only through the router. A 405 can come
        from a handler that refuses; the claim here is that there is nothing to
        refuse with, so nobody can later mis-guard it."""
        for verb in self.WRITES:
            with self.subTest(verb=verb):
                self.assertFalse(hasattr(views.CohortBoardView, verb))
                self.assertFalse(hasattr(views.CohortsView, verb))

    def test_no_request_through_the_cohort_surface_can_change_a_proof(self):
        """The whole feature's credibility in one assertion: every verb against
        every cohort URL, then the proof rows read back."""
        before = list(
            CheckIn.objects.filter(goal=self.goal)
            .order_by("id")
            .values("id", "phase", "proof_status", "pm_proof_text", "proof_parts")
        )
        urls = [
            "/api/coach/cohorts/",
            "/api/coach/cohorts/join/",
            f"/api/coach/cohorts/{self.cohort.id}/",
            f"/api/coach/cohorts/{self.cohort.id}/membership/",
        ]
        payload = {
            "proof_status": "ACCEPTED",
            "phase": "TRACTION",
            "code": self.cohort.join_code,
            "goal": self.goal.id,
            "user": self.bob.id,
        }
        for url in urls:
            for verb in ["get", *self.WRITES]:
                getattr(self.client, verb)(url, payload)

        after = list(
            CheckIn.objects.filter(goal=self.goal)
            .order_by("id")
            .values("id", "phase", "proof_status", "pm_proof_text", "proof_parts")
        )
        self.assertEqual(before, after)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.phase, Phase.IDEA)

    def test_the_cohort_surface_cannot_name_another_builder(self):
        """Neither write takes a user. Alice asking to remove Bob removes
        Alice, because `request.user` is the only user either view can spell."""
        self.client.delete(
            f"/api/coach/cohorts/{self.cohort.id}/membership/", {"user": self.bob.id}
        )
        remaining = set(
            CohortMember.objects.filter(cohort=self.cohort).values_list(
                "user_id", flat=True
            )
        )
        self.assertEqual(remaining, {self.bob.id})

    def test_there_is_no_route_that_makes_or_unmakes_a_cohort(self):
        """A cohort comes from the admin. The product surface has no create,
        rename or delete, so a coordinator's whole capability is holding a
        code."""
        self.assertEqual(self.client.post("/api/coach/cohorts/", {"name": "x"}).status_code, 405)
        self.assertEqual(
            self.client.delete(f"/api/coach/cohorts/{self.cohort.id}/").status_code, 405
        )

    def test_signing_out_closes_every_cohort_surface(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/coach/cohorts/").status_code, 401)
        self.assertEqual(
            self.client.get(f"/api/coach/cohorts/{self.cohort.id}/").status_code, 401
        )
        self.assertEqual(
            self.client.post(
                "/api/coach/cohorts/join/", {"code": self.cohort.join_code}
            ).status_code,
            401,
        )


class CohortBoardTests(CohortTestCase):
    """What the board says, and — as much — what it refuses to say."""

    def setUp(self):
        super().setUp()
        self.cohort = self.make_cohort()
        self.join(self.cohort, self.alice)

    def test_the_board_carries_counts_and_not_one_word_the_builder_typed(self):
        """Nothing self-reported appears anywhere on it. The goal's title, its
        brief, every proof text and every retirement reason are the builder's
        own words, and a board carrying them is a deck with extra steps."""
        goal = self.make_goal(title="Secret tiffin idea", phase=Phase.VALIDATION)
        goal.brief = {"text": "a private sketch"}
        goal.save(update_fields=["brief"])
        self.bank(goal, Phase.VALIDATION, 2)

        body = self.client.get(f"/api/coach/cohorts/{self.cohort.id}/").json()
        blob = json.dumps(body)
        for typed in ["Secret tiffin idea", "a private sketch", "notes from the talk"]:
            self.assertNotIn(typed, blob)
        self.assertNotIn(self.alice.email, blob)

        row = body["board"][0]
        self.assertEqual(
            set(row),
            {
                "name",
                "rank",
                "has_goal",
                "phase",
                "phase_index",
                "accepted_proofs",
                "contact_proofs",
                "streak",
            },
        )

    def test_the_counts_are_the_gates_own(self):
        """`accepted_proofs` is every accepted proof whatever phase stamped it,
        and `contact_proofs` is the VALIDATION-onward subset — the same split
        `gates.py` makes, and the same one the shared record already shows."""
        goal = self.make_goal(phase=Phase.BUILD)
        self.bank(goal, Phase.IDEA, 1)
        self.bank(goal, Phase.VALIDATION, 3)
        self.bank(goal, Phase.BUILD, 2)
        self.bank(goal, Phase.BUILD, 4, accepted=False)

        row = self.client.get(f"/api/coach/cohorts/{self.cohort.id}/").json()["board"][0]
        self.assertEqual(row["accepted_proofs"], 6)
        self.assertEqual(row["contact_proofs"], 5)
        self.assertEqual(row["phase"], Phase.BUILD)

    def test_a_member_between_ideas_shows_as_having_none(self):
        """Not hidden, and not backfilled from a retired goal: "closed their
        idea last week" and "three weeks into VALIDATION" are different facts
        and the board must not blur them."""
        closed = self.make_goal(status=Goal.Status.ABANDONED)
        self.bank(closed, Phase.VALIDATION, 4)

        row = self.client.get(f"/api/coach/cohorts/{self.cohort.id}/").json()["board"][0]
        self.assertFalse(row["has_goal"])
        self.assertIsNone(row["phase"])
        self.assertIsNone(row["rank"])
        self.assertEqual(row["accepted_proofs"], 0)

    def test_the_board_ranks_on_contact_proofs_first(self):
        """The coordinator's actual question — which of these forty talked to
        somebody — and every one of those proofs cleared a gate."""
        for name, idea_proofs, contact_proofs in [
            ("deck", 9, 0),
            ("talker", 0, 4),
            ("middling", 1, 2),
        ]:
            user = make_user(name)
            self.join(self.cohort, user)
            goal = self.make_goal(user=user, phase=Phase.VALIDATION)
            self.bank(goal, Phase.IDEA, idea_proofs)
            self.bank(goal, Phase.VALIDATION, contact_proofs)

        board = self.client.get(f"/api/coach/cohorts/{self.cohort.id}/").json()["board"]
        self.assertEqual(
            [row["name"] for row in board[:3]], ["talker", "middling", "deck"]
        )
        # …and alice, who has no goal, is last and unranked.
        self.assertEqual(board[-1]["name"], "alice")
        self.assertIsNone(board[-1]["rank"])

    def test_a_tie_shares_a_place_rather_than_being_broken_arbitrarily(self):
        """Two builders on identical counts are not fourth and fifth. Picking
        one would be the board inventing a difference the record does not
        contain."""
        for name in ["twin_a", "twin_b", "ahead"]:
            user = make_user(name)
            self.join(self.cohort, user)
            goal = self.make_goal(user=user, phase=Phase.VALIDATION)
            self.bank(goal, Phase.VALIDATION, 5 if name == "ahead" else 2)

        board = self.client.get(f"/api/coach/cohorts/{self.cohort.id}/").json()["board"]
        ranked = {row["name"]: row["rank"] for row in board}
        self.assertEqual(ranked["ahead"], 1)
        self.assertEqual(ranked["twin_a"], 2)
        self.assertEqual(ranked["twin_b"], 2)

    def test_the_streak_is_the_same_one_the_builders_own_dashboard_shows(self):
        goal = self.make_goal()
        self.complete_days(goal, [0, 1, 2, 4])

        row = self.client.get(f"/api/coach/cohorts/{self.cohort.id}/").json()["board"][0]
        self.assertEqual(row["streak"], 3)
        self.assertEqual(row["streak"], streaks.current_streak(goal, date.today()))

    def test_a_soft_deleted_goal_is_off_the_board(self):
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.bank(goal, Phase.VALIDATION, 3)
        goal.delete()  # soft

        row = self.client.get(f"/api/coach/cohorts/{self.cohort.id}/").json()["board"][0]
        self.assertFalse(row["has_goal"])
        self.assertEqual(row["accepted_proofs"], 0)


class CohortCountsAgreeTests(CohortTestCase):
    """The aggregate and the per-goal helpers are the same arithmetic.

    `cohorts.py` counts in the database because forty `gates.accepted_proofs_
    total(goal)` calls are forty queries on a 0.1-CPU instance. The risk that
    buys is a second definition of a number this product's whole argument rests
    on, and the only honest answer to it is to check them against each other
    rather than to promise they match.
    """

    def _spread(self):
        """Goals shaped every way the counts can disagree: an empty one, one
        that never left IDEA, one banking across three phases, one with
        refused and unjudged rows in the way, one with a broken streak."""
        shapes = [
            (Phase.IDEA, []),
            (Phase.IDEA, [(Phase.IDEA, 2, True)]),
            (Phase.BUILD, [(Phase.IDEA, 1, True), (Phase.VALIDATION, 3, True), (Phase.BUILD, 2, True)]),
            (Phase.VALIDATION, [(Phase.VALIDATION, 2, True), (Phase.VALIDATION, 4, False)]),
            (Phase.TRACTION, [(Phase.LAUNCH, 5, True), (Phase.TRACTION, 1, True)]),
        ]
        cohort = self.make_cohort()
        goals = []
        for i, (phase, banks) in enumerate(shapes):
            user = make_user(f"spread{i}")
            self.join(cohort, user)
            goal = self.make_goal(user=user, phase=phase)
            for stamped, n, accepted in banks:
                self.bank(goal, stamped, n, accepted=accepted)
            self.complete_days(goal, list(range(i)) + [i + 3])
            goals.append(goal)
        return cohort, goals

    def test_every_column_matches_the_helper_it_came_from(self):
        cohort, goals = self._spread()
        today = date.today()
        rows = {row["name"]: row for row in cohorts.board(cohort, today)}

        for goal in goals:
            with self.subTest(goal=goal.id):
                row = rows[goal.user.username]
                self.assertEqual(
                    row["accepted_proofs"], gates.accepted_proofs_total(goal)
                )
                self.assertEqual(row["contact_proofs"], gates.contact_proofs(goal))
                self.assertEqual(row["streak"], streaks.current_streak(goal, today))
                self.assertEqual(row["phase"], goal.phase)

    def test_the_contact_subset_is_the_gates_own_list_of_phases(self):
        """Read from `gates.CONTACT_PHASES` rather than spelled again, so a
        phase added to the ladder reaches both counts at once."""
        self.assertIn(Phase.VALIDATION, gates.CONTACT_PHASES)
        self.assertNotIn(Phase.IDEA, gates.CONTACT_PHASES)

        cohort = self.make_cohort()
        self.join(cohort, self.alice)
        goal = self.make_goal(phase=Phase.VALIDATION)
        for phase in Phase:
            self.bank(goal, phase, 1)

        row = cohorts.board(cohort, date.today())[0]
        self.assertEqual(row["contact_proofs"], len(gates.CONTACT_PHASES))
        self.assertEqual(row["accepted_proofs"], len(Phase.choices))

    def test_there_is_one_streak_walk_and_both_callers_use_it(self):
        """`streaks.current_streak` is `streak_from` over the goal's own days.
        A second copy of the walk is how a cohort board and a builder's own
        dashboard end up disagreeing about the same week."""
        goal = self.make_goal()
        self.complete_days(goal, [0, 1, 2, 5, 6])
        today = date.today()
        self.assertEqual(
            streaks.current_streak(goal, today),
            streaks.streak_from(streaks._complete_dates(goal), today),
        )


class CohortBoardQueryTests(CohortTestCase):
    """Forty members each needing counts is the natural N+1, and this runs on
    one worker with 0.1 CPU. The board's cost must not move with its size."""

    #: What `cohorts.board` issues: the members, their active goals, one
    #: grouped proof count, one read of complete days.
    BOARD_QUERIES = 4
    #: What the whole request issues: the four above, plus the membership check
    #: that scopes the board to a cohort the requester is in.
    #:
    #: Measured under `force_authenticate`, which hands DRF a user object and
    #: so skips the one lookup `CookieJWTAuthentication` does from the access
    #: cookie. A real signed-in request is therefore this plus one — and that
    #: one is per REQUEST, not per member, which is the property being pinned.
    ENDPOINT_QUERIES = 5

    def _cohort_of(self, n: int) -> Cohort:
        cohort = self.make_cohort(f"Cohort of {n}")
        for i in range(n):
            user = make_user(f"member{n}_{i}")
            self.join(cohort, user)
            goal = self.make_goal(user=user, phase=Phase.VALIDATION)
            self.bank(goal, Phase.VALIDATION, 3)
            self.complete_days(goal, [1, 2])
        return cohort

    def test_a_forty_member_board_costs_the_same_as_a_two_member_one(self):
        """The number in the docstring, asserted. An N+1 reintroduced by a
        later `select_related` somebody removed would otherwise go unnoticed
        until it was slow for the cohort that mattered."""
        small = self._cohort_of(2)
        forty = self._cohort_of(40)
        today = date.today()

        with self.assertNumQueries(self.BOARD_QUERIES):
            cohorts.board(small, today)
        with self.assertNumQueries(self.BOARD_QUERIES):
            rows = cohorts.board(forty, today)
        self.assertEqual(len(rows), 40)
        self.assertEqual(rows[0]["contact_proofs"], 3)

    def test_an_empty_cohort_asks_nothing_further(self):
        """No members means no goals to look up — the aggregates must not run
        an `IN ()` each."""
        empty = self.make_cohort("Nobody yet")
        with self.assertNumQueries(1):
            self.assertEqual(cohorts.board(empty, date.today()), [])

    def test_a_cohort_where_nobody_has_a_goal_asks_nothing_further(self):
        cohort = self.make_cohort("Between ideas")
        for i in range(5):
            self.join(cohort, make_user(f"idle{i}"))
        with self.assertNumQueries(2):
            rows = cohorts.board(cohort, date.today())
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["rank"] is None for row in rows))

    def test_the_active_goal_lookup_takes_the_index_that_already_exists(self):
        """No new index ships with this feature. This is the half of that claim
        which is a clean fit: `coach_goal_active_idx` leads with `user`, and the
        board asks for forty of them."""
        self._cohort_of(4)
        self.assertIn(
            "coach_goal_active_idx",
            Goal.objects.filter(
                user_id__in=[1, 2, 3], status=Goal.Status.ACTIVE
            ).explain(),
        )

    def test_the_complete_days_read_does_not_sort_rows_it_puts_into_a_set(self):
        """`CheckIn.Meta.ordering` is `["-date"]`, and Django applies a model's
        default ordering to a `values_list` — so this read sorted every row the
        cohort had ever written, to fill sets that have no order. The plan said
        `USE TEMP B-TREE FOR ORDER BY` over all of them.

        Pinned on the plan rather than on the call, because `.order_by()` is one
        token and looks removable to anybody tidying the file."""
        cohort = self._cohort_of(4)
        goal_ids = list(
            Goal.objects.filter(
                user__cohort_memberships__cohort=cohort, status=Goal.Status.ACTIVE
            ).values_list("id", flat=True)
        )
        plan = (
            CheckIn.objects.filter(goal_id__in=goal_ids)
            .exclude(am_declaration="")
            .exclude(pm_proof_text="")
            .values_list("goal_id", "date")
            .order_by()
            .explain()
        )
        self.assertNotIn("TEMP B-TREE", plan.upper())

    def test_the_proof_aggregate_does_not_group_by_the_models_default_ordering(self):
        """The same trap, and here it is correctness rather than cost. Django
        appends the default ordering to the GROUP BY of a `values()` aggregate,
        which would group by (goal, date) and return one row per DAY — every
        count coming back 1 on a fixture that banks one proof an evening, which
        is what every fixture looks like."""
        cohort = self._cohort_of(3)
        rows = cohorts.board(cohort, date.today())
        self.assertTrue(all(row["accepted_proofs"] == 3 for row in rows))

    def test_the_endpoint_itself_is_flat_in_the_cohorts_size(self):
        """`board()` is four queries; the request around it adds the membership
        check that scopes it. The number quoted in the pull request is THIS one
        — what the free-tier instance actually serves — and the claim being
        pinned is not the value but its FLATNESS: two builders and forty cost
        the same, so the N+1 cannot come back unnoticed."""
        two = self._cohort_of(2)
        forty = self._cohort_of(40)
        self.client.force_authenticate(None)
        member = CohortMember.objects.filter(cohort=forty).first().user
        self.client.force_authenticate(member)
        # Warm anything cached per-process (throttle buckets, content types) so
        # the two measurements below differ only in cohort size.
        self.client.get(f"/api/coach/cohorts/{forty.id}/")

        with self.assertNumQueries(self.ENDPOINT_QUERIES):
            big = self.client.get(f"/api/coach/cohorts/{forty.id}/")
        self.client.force_authenticate(
            CohortMember.objects.filter(cohort=two).first().user
        )
        self.client.get(f"/api/coach/cohorts/{two.id}/")
        with self.assertNumQueries(self.ENDPOINT_QUERIES):
            small = self.client.get(f"/api/coach/cohorts/{two.id}/")

        self.assertEqual(len(big.json()["board"]), 40)
        self.assertEqual(len(small.json()["board"]), 2)
