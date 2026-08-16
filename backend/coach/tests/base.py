"""Shared ground for every module in this package: the user factory, the base
case that stubs the network away, and the state helper two modules read.
"""

from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from .. import gates
from ..models import (
    CheckIn,
    Goal,
    Phase,
)

User = get_user_model()


def make_user(name: str):
    return User.objects.create_user(
        username=name, email=f"{name}@example.com", password="pw"
    )


class CoachTestCase(APITestCase):
    def setUp(self):
        # Throttle counters live in the process cache, keyed by user pk — and
        # every test here recreates alice as pk 1, so without this the suite
        # accumulates one shared history and the tests that file several proofs
        # start being refused by the tests that ran before them. Nothing about
        # the throttle is per-test state; the cache is simply not part of what
        # the test database rolls back.
        cache.clear()
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.client.force_authenticate(self.alice)
        # No test reaches the network. Failing by default is deliberate: every
        # path that calls a model has a deterministic floor, and this makes
        # the whole suite exercise it unless a test says otherwise. Tests that
        # want a specific reply patch this again — the inner patch wins.
        patcher = mock.patch(
            "coach.views.llm.complete", side_effect=RuntimeError("no LLM in tests")
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # The same rule for the second thing that reaches out of the process.
        # A proof can carry a link and the prove path opens it, so without this
        # the suite would make real requests to whatever a test happened to
        # type. Raising rather than returning None keeps coach.links' own
        # degrade-to-unchecked path under test on every proof that has a URL.
        no_net = mock.patch(
            "coach.links._fetch", side_effect=RuntimeError("no network in tests")
        )
        no_net.start()
        self.addCleanup(no_net.stop)

    def make_goal(self, user=None, **kwargs) -> Goal:
        kwargs.setdefault("title", "Tiffin app")
        return Goal.objects.create(user=user or self.alice, **kwargs)

    def _days(self, goal: Goal, n: int):
        """n declared days, newest first, one per date — enough rows to push a
        goal past a payload cap. Declarations only: the callers are asking how
        many rows a view hands back, not what the gate makes of them.
        """
        CheckIn.objects.bulk_create(
            CheckIn(
                goal=goal,
                date=date.today() - timedelta(days=i),
                phase=goal.phase,
                am_declaration=f"day {i}",
            )
            for i in range(n)
        )

    def accept_proofs(self, goal: Goal, n: int):
        """Bank n accepted proofs in the goal's CURRENT phase — the gate
        attributes by the stamped phase, exactly as the views write it.

        Rows are labelled with whatever KINDS of evidence the phase requires
        (gates.Need.kinds), because that is what "n accepted proofs" means to
        every caller here: the builder did the work this phase asks for. A
        deliberately unlabelled row is a different scenario and the tests that
        want one say so — see GateCountsPeopleAndKindsTests. Subjects stay blank:
        an unlabelled proof counts as its own person by design, so a caller
        banking three of them still gets three.
        """
        need = gates.PROOFS_REQUIRED.get(Phase(goal.phase))
        kinds = list(need.kinds) if need else []
        for i in range(n):
            CheckIn.objects.create(
                goal=goal,
                date=date.today() - timedelta(days=i),
                phase=goal.phase,
                am_declaration="talk to a customer",
                pm_proof_text="notes from the talk",
                proof_status=CheckIn.ProofStatus.ACCEPTED,
                proof_parts=kinds,
            )


def _state_launch(client) -> dict:
    return client.get("/api/coach/state/").json()["launch"]
