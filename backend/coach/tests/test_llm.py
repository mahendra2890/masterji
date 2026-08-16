"""The model seam — `llm.py`, and the ledger `spend.py` keeps of it: timeouts,
the per-request budget, the breaker, which tier each call gets, and what every
call cost and who caused it.
"""

from datetime import date
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APITestCase

from ..models import (
    CheckIn,
    Goal,
    Message,
    Phase,
)
from .base import CoachTestCase, make_user

# --- the LLM seam ------------------------------------------------------------


class LlmSeamTests(SimpleTestCase):
    """Every model call must carry a timeout. Without one, a hung provider
    holds a gunicorn thread until the health check starts failing — that is
    an outage, discovered the hard way on the free instance.

    Deliberately NOT a CoachTestCase: that base patches llm.complete away,
    and these tests exist to exercise the real seam functions."""

    def fake_response(self):
        message = mock.Mock()
        message.content = "ok"
        choice = mock.Mock()
        choice.message = message
        response = mock.Mock()
        response.choices = [choice]
        return response

    def test_complete_is_bounded(self):
        from django.conf import settings as s

        from .. import llm

        with mock.patch("coach.llm.litellm.completion", return_value=self.fake_response()) as call:
            llm.complete("system", "user")
        self.assertEqual(call.call_args.kwargs["timeout"], s.LLM_TIMEOUT_S)

    def test_complete_with_image_is_bounded(self):
        from django.conf import settings as s

        from .. import llm

        with mock.patch("coach.llm.litellm.completion", return_value=self.fake_response()) as call:
            llm.complete_with_image("system", "user", b"\x89PNG", "image/png")
        self.assertEqual(call.call_args.kwargs["timeout"], s.LLM_TIMEOUT_S)

    def test_stream_chat_is_bounded(self):
        from django.conf import settings as s

        from .. import llm

        with mock.patch("coach.llm.litellm.completion", return_value=iter([])) as call:
            list(llm.stream_chat("system", []))
        self.assertEqual(call.call_args.kwargs["timeout"], s.LLM_TIMEOUT_S)

    def test_complete_talks_with_the_chat_model_by_default(self):
        from django.conf import settings as s

        from .. import llm

        with mock.patch(
            "coach.llm.litellm.completion", return_value=self.fake_response()
        ) as call:
            llm.complete("system", "user")
        self.assertEqual(call.call_args.kwargs["model"], s.LLM_MODEL)

    def test_complete_takes_a_model_for_callers_that_are_not_conversation(self):
        from .. import llm

        with mock.patch(
            "coach.llm.litellm.completion", return_value=self.fake_response()
        ) as call:
            llm.complete("system", "user", model="anthropic/claude-sonnet-5")
        self.assertEqual(
            call.call_args.kwargs["model"], "anthropic/claude-sonnet-5"
        )


def _ok_response(usage=None):
    """What litellm hands back on a good call."""
    message = mock.Mock()
    message.content = "ok"
    choice = mock.Mock()
    choice.message = message
    return mock.Mock(choices=[choice], usage=usage)


def _tokens(prompt, completion, total):
    return mock.Mock(
        prompt_tokens=prompt, completion_tokens=completion, total_tokens=total
    )


def _recorded(span):
    return dict(call.args for call in span.set_attribute.call_args_list)


class LlmAccountingTests(TestCase):
    """What a call cost, on the call's own span.

    A TestCase rather than a SimpleTestCase since the ledger landed: the seam
    now writes a ModelCall row for any call that reports usage, and two of the
    tests below report some. spend.record swallows its own failures, so under
    SimpleTestCase these would still pass — while logging a database error per
    run and proving nothing about the row. The database is the honest fixture.

    A span per call and not attributes on coach.turn, because one request can
    make several calls and the parent would keep only the last — a silent
    undercount of the exact number this exists to produce. Nothing in here may
    raise: a token count is worth having and never worth a builder's turn.
    """

    def test_the_tokens_land_on_the_span(self):
        from .. import llm

        span = mock.Mock()
        with (
            mock.patch("coach.llm.tracer.start_span", return_value=span),
            mock.patch(
                "coach.llm.litellm.completion",
                return_value=_ok_response(_tokens(1200, 80, 1280)),
            ),
        ):
            llm.complete("system", "user")
        recorded = _recorded(span)
        self.assertEqual(recorded["llm.usage.prompt_tokens"], 1200)
        self.assertEqual(recorded["llm.usage.completion_tokens"], 80)
        self.assertEqual(recorded["llm.usage.total_tokens"], 1280)

    def test_the_span_says_which_model_was_asked(self):
        """Three models are reachable from this seam and they do not cost the
        same. A token count with no model beside it prices nothing."""
        from .. import llm

        span = mock.Mock()
        with (
            mock.patch("coach.llm.tracer.start_span", return_value=span),
            mock.patch("coach.llm.litellm.completion", return_value=_ok_response()),
        ):
            llm.complete("system", "user", model="anthropic/claude-sonnet-5")
        self.assertEqual(_recorded(span)["llm.model"], "anthropic/claude-sonnet-5")

    def test_a_response_with_no_usage_costs_nothing(self):
        """Some providers do not report it. Absent numbers are not an error,
        and the turn must not know the difference."""
        from .. import llm

        span = mock.Mock()
        with (
            mock.patch("coach.llm.tracer.start_span", return_value=span),
            mock.patch("coach.llm.litellm.completion", return_value=_ok_response()),
        ):
            self.assertEqual(llm.complete("system", "user"), "ok")
        self.assertNotIn("llm.usage.total_tokens", _recorded(span))

    def test_a_stream_asks_for_its_usage(self):
        """A streamed call reports nothing unless it is asked at the door."""
        from .. import llm

        with mock.patch(
            "coach.llm.litellm.completion", return_value=iter([])
        ) as call:
            list(llm.stream_chat("system", []))
        self.assertEqual(
            call.call_args.kwargs["stream_options"], {"include_usage": True}
        )

    def test_the_usage_chunk_does_not_break_the_stream(self):
        """It arrives last and carries no choices at all. Reading one would
        turn accounting into an IndexError in the middle of a sentence."""
        from .. import llm

        spoken = mock.Mock(
            choices=[mock.Mock(delta=mock.Mock(content="hello", tool_calls=None))],
            usage=None,
        )
        final = mock.Mock(choices=[], usage=_tokens(5, 2, 7))
        span = mock.Mock()
        with (
            mock.patch("coach.llm.tracer.start_span", return_value=span),
            mock.patch(
                "coach.llm.litellm.completion", return_value=iter([spoken, final])
            ),
        ):
            spoken_out = list(llm.stream_chat("system", []))
        self.assertEqual(spoken_out, [("delta", "hello")])
        self.assertEqual(_recorded(span)["llm.usage.total_tokens"], 7)


class LlmBudgetTests(SimpleTestCase):
    """One request may spend LLM_REQUEST_BUDGET_S talking to a provider.

    LLM_TIMEOUT_S bounds a single call; this bounds their sum, which is what
    num_retries could otherwise stack past on a box with twelve threads.
    """

    def setUp(self):
        from .. import llm

        self.addCleanup(llm.clear_budget)

    def test_without_a_request_there_is_no_deadline(self):
        """A shell and a management command get exactly the behaviour that
        existed before the budget did."""
        from django.conf import settings as s

        from .. import llm

        with mock.patch(
            "coach.llm.litellm.completion", return_value=_ok_response()
        ) as call:
            llm.complete("system", "user")
        self.assertEqual(call.call_args.kwargs["timeout"], s.LLM_TIMEOUT_S)
        self.assertEqual(call.call_args.kwargs["num_retries"], llm.RETRIES)

    @override_settings(LLM_REQUEST_BUDGET_S=300)
    def test_the_first_call_of_a_request_gets_the_whole_timeout(self):
        """Nothing a builder does today gets slower. The budget only ever
        takes from what comes after the first call."""
        from django.conf import settings as s

        from .. import llm

        llm.begin_budget()
        with mock.patch(
            "coach.llm.litellm.completion", return_value=_ok_response()
        ) as call:
            llm.complete("system", "user")
        self.assertEqual(call.call_args.kwargs["timeout"], s.LLM_TIMEOUT_S)
        self.assertEqual(call.call_args.kwargs["num_retries"], llm.RETRIES)

    @override_settings(LLM_REQUEST_BUDGET_S=61, LLM_TIMEOUT_S=60)
    def test_the_retries_go_first(self):
        """A retry that cannot finish inside the budget is a thread held for
        nothing — so the budget stops buying them before it stops buying
        calls."""
        from .. import llm

        llm.begin_budget()
        with mock.patch(
            "coach.llm.litellm.completion", return_value=_ok_response()
        ) as call:
            llm.complete("system", "user")
        self.assertEqual(call.call_args.kwargs["num_retries"], 0)

    @override_settings(LLM_REQUEST_BUDGET_S=0)
    def test_a_spent_budget_refuses_without_asking_the_provider(self):
        """The point of the ceiling: the thread comes back rather than paying
        one more full timeout to reach a fallback it can reach now."""
        from .. import llm

        llm.begin_budget()
        with mock.patch("coach.llm.litellm.completion") as call:
            with self.assertRaises(llm.LlmUnavailable):
                llm.complete("system", "user")
        call.assert_not_called()


@override_settings(
    LLM_BREAKER_FAILURES=3,
    LLM_BREAKER_COOLDOWN_S=30,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "llm-breaker-tests",
        }
    },
)
class LlmBreakerTests(SimpleTestCase):
    """Degrading per SERVICE, not only per call.

    UNJUDGED already means an outage costs the gate credit and not the day.
    What it could not do was arrive quickly: during a wobble every request
    paid the full timeout on its way to a fallback it was always going to
    reach, so the graceful path was too slow to keep the app up.
    """

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def fail(self, llm, times):
        for _ in range(times):
            with mock.patch(
                "coach.llm.litellm.completion", side_effect=RuntimeError("down")
            ):
                with self.assertRaises(RuntimeError):
                    llm.complete("system", "user")

    def test_consecutive_failures_stop_the_seam_asking(self):
        from .. import llm

        self.fail(llm, 3)
        with mock.patch("coach.llm.litellm.completion") as call:
            with self.assertRaises(llm.LlmUnavailable):
                llm.complete("system", "user")
        call.assert_not_called()

    def test_a_working_call_resets_the_count(self):
        """Failures scattered around calls that worked are not a wobble, and
        must not add up into one over an afternoon."""
        from .. import llm

        self.fail(llm, 2)
        with mock.patch("coach.llm.litellm.completion", return_value=_ok_response()):
            llm.complete("system", "user")
        self.fail(llm, 2)
        with mock.patch(
            "coach.llm.litellm.completion", return_value=_ok_response()
        ) as call:
            llm.complete("system", "user")
        call.assert_called_once()

    def test_the_refusal_is_not_itself_a_failure(self):
        """Otherwise the breaker feeds itself: every refused call would be a
        fresh failure and the cooldown would never end."""
        from .. import llm

        self.fail(llm, 3)
        for _ in range(3):
            with self.assertRaises(llm.LlmUnavailable):
                llm.complete("system", "user")
        self.assertIsNone(cache.get("llm:breaker:failures"))


class ModelTierTests(SimpleTestCase):
    """Which model each call gets, and why they are not all one.

    A weak turn of conversation is a weak turn of conversation. A wrong verdict
    either banks a proof that isn't there or sends a builder who did the work
    away to rewrite it, and the second one is how this product loses people. So
    the two calls that decide something recorded on the row are their own
    setting, and the ladder is arranged so upgrading the judge cannot leave half
    a verdict behind on the cheap model.
    """

    def test_unset_changes_nothing(self):
        """The whole ladder collapses to one model when nobody configures it,
        so shipping this seam is not shipping a behaviour change."""
        from django.conf import settings as s

        self.assertEqual(s.LLM_JUDGE_MODEL, s.LLM_MODEL)
        self.assertEqual(s.LLM_VISION_MODEL, s.LLM_MODEL)

    @override_settings(LLM_JUDGE_MODEL="anthropic/claude-sonnet-5")
    def test_the_judge_model_is_its_own_setting(self):
        from django.conf import settings as s

        self.assertNotEqual(s.LLM_JUDGE_MODEL, s.LLM_MODEL)

    def test_vision_chains_off_the_judge_and_not_the_chat(self):
        """The trap this removes: a screenshot silently graded by the cheap model
        after the judge was upgraded.

        Read off the module source, not the resolved setting, because the
        DEFAULTING is what is under test and it resolves once at import —
        override_settings moves LLM_JUDGE_MODEL without re-running the fallback,
        so a runtime assertion here would pass whatever the chain said.

        Matched on the assignment line mentioning LLM_JUDGE_MODEL rather than on
        a whole expression: the fallback's target is the claim, and reformatting
        the file is not a regression.
        """
        import inspect

        from config import settings as module

        line = next(
            ln
            for ln in inspect.getsource(module).splitlines()
            if ln.startswith("LLM_VISION_MODEL")
        )
        self.assertIn("LLM_JUDGE_MODEL", line)


class VerdictsGetTheJudgeModelTests(CoachTestCase):
    """The two call sites, end to end through the API."""

    def test_the_evening_verdict_uses_the_judge_model(self):
        self.make_goal(phase=Phase.VALIDATION)
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Ramesh"})
        with override_settings(LLM_JUDGE_MODEL="anthropic/claude-sonnet-5"):
            with mock.patch(
                "coach.views.llm.complete",
                return_value='{"verdict": "accept", "reaction": "ok"}',
            ) as called:
                self.client.post(
                    "/api/coach/checkins/prove/", {"text": "Spoke to Ramesh."}
                )
        self.assertEqual(
            called.call_args.kwargs["model"], "anthropic/claude-sonnet-5"
        )

    def test_the_morning_verdict_uses_the_judge_model(self):
        goal = self.make_goal()
        self.client.post("/api/coach/checkins/declare/", {"text": "write the problem"})
        checkin = CheckIn.objects.get(goal=goal)
        with override_settings(LLM_JUDGE_MODEL="anthropic/claude-sonnet-5"):
            with mock.patch(
                "coach.views.llm.complete",
                return_value='{"fit": "on_phase", "reaction": "", "proof_ask": "x"}',
            ) as called:
                self.client.post(f"/api/coach/checkins/{checkin.pk}/judge/")
        self.assertEqual(
            called.call_args.kwargs["model"], "anthropic/claude-sonnet-5"
        )

    def test_the_retirement_sentence_does_not(self):
        """gates.reads_as already decided the verdict here, out of proofs the
        builder had to earn. All the model contributes is the sentence, so it
        belongs with the conversation — stated as a decision, not left as an
        omission."""
        goal = self.make_goal()
        with override_settings(LLM_JUDGE_MODEL="anthropic/claude-sonnet-5"):
            with mock.patch(
                "coach.views.llm.complete", return_value="Closed."
            ) as called:
                self.client.post(
                    f"/api/coach/goals/{goal.id}/retire/", {"reason": "it died"}
                )
        self.assertNotIn("model", called.call_args.kwargs)

    def test_the_chat_does_not(self):
        self.make_goal()
        with override_settings(LLM_JUDGE_MODEL="anthropic/claude-sonnet-5"):
            with mock.patch(
                "coach.views.llm.stream_chat", return_value=iter([("delta", "ok")])
            ) as called:
                response = self.client.post("/api/coach/chat/", {"content": "hi"})
                b"".join(response.streaming_content)
        self.assertNotIn("model", called.call_args.kwargs)

    def stream_of(self, *fragments):
        """A streamed tool call as providers actually send one: the name in
        the first fragment, the arguments dribbled out as JSON text."""
        chunks = []
        for name, arguments in fragments:
            call = mock.Mock()
            call.index = 0
            call.function = mock.Mock(name_=name)
            call.function.name = name
            call.function.arguments = arguments
            delta = mock.Mock()
            delta.content = None
            delta.tool_calls = [call]
            chunk = mock.Mock()
            chunk.choices = [mock.Mock(delta=delta)]
            chunks.append(chunk)
        return chunks

    def test_tool_arguments_are_reassembled_across_chunks(self):
        """suggest_proof carries a whole paragraph of proof text. Arriving in
        fragments, it is worthless unless the seam puts it back together."""
        from .. import llm

        stream = self.stream_of(
            ("suggest_proof", '{"text": "Spoke to '),
            (None, 'Ramesh. 40 plates wasted."}'),
        )
        with mock.patch("coach.llm.litellm.completion", return_value=iter(stream)):
            calls = [p for kind, p in llm.stream_chat("system", []) if kind == "tool_call"]
        self.assertEqual(
            calls,
            [
                {
                    "name": "suggest_proof",
                    "arguments": {"text": "Spoke to Ramesh. 40 plates wasted."},
                }
            ],
        )

    def test_malformed_arguments_cost_the_call_not_the_turn(self):
        """Every tool here is a proposal the server re-decides, so a call with
        nothing in it goes nowhere. A raised exception would instead take down
        a conversation the builder was in the middle of."""
        from .. import llm

        stream = self.stream_of(("suggest_proof", '{"text": "unterminated'))
        with mock.patch("coach.llm.litellm.completion", return_value=iter(stream)):
            calls = [p for kind, p in llm.stream_chat("system", []) if kind == "tool_call"]
        self.assertEqual(calls, [{"name": "suggest_proof", "arguments": {}}])

    def test_a_tool_call_and_a_usage_chunk_survive_each_other(self):
        """The two halves in one stream, which is every real tool-calling turn.

        Both were already covered apart and neither covered together, so #290
        lived in the gap for a day: the loop over `delta.tool_calls` bound
        `call`, the same name the `with` above holds the in-flight _Call under,
        and Python binds a for-target only when the loop iterates. So the seam
        was right whenever the model stayed quiet and clobbered the moment it
        reached for a tool — and the next chunk's usage went to the fragment.

        Driven live against openai/gpt-5.4-mini on 15 August 2026: the provider
        sends its tool-call chunks first and the usage chunk last (index 21 of
        22), so this ordering is the real one and not a worst case invented
        here.

        REAL litellm types, not mock.Mock, and that is the load-bearing part of
        this test. A Mock invents any attribute asked of it, so the clobbered
        object would have accepted `.usage` and this would have passed against
        the bug — which is exactly how the two tests above missed it.
        ChatCompletionDeltaToolCall is a pydantic model and raises, which is
        what took the turn down in production.
        """
        from litellm.types.utils import (
            ChatCompletionDeltaToolCall,
            Delta,
            Function,
            ModelResponseStream,
        )

        from .. import llm

        fragment = ChatCompletionDeltaToolCall(
            id="call_1",
            type="function",
            index=0,
            function=Function(name="suggest_proof", arguments='{"text": "spoke to Ramesh"}'),
        )
        tool_chunk = ModelResponseStream(
            choices=[{"index": 0, "delta": Delta(content=None, tool_calls=[fragment])}]
        )
        usage_chunk = ModelResponseStream(choices=[])
        usage_chunk.usage = _tokens(1200, 300, 1500)

        recorded = {}
        with (
            mock.patch(
                "coach.llm.litellm.completion",
                return_value=iter([tool_chunk, usage_chunk]),
            ),
            mock.patch(
                "coach.llm.spend.record", side_effect=lambda **kw: recorded.update(kw)
            ),
        ):
            calls = [p for kind, p in llm.stream_chat("system", []) if kind == "tool_call"]

        # The tool call still reaches the view. Without the fix the stream
        # raised before it was ever yielded, so the builder got STREAM_BROKE
        # and no drafted proof, no gate check and no close box.
        self.assertEqual(
            calls,
            [{"name": "suggest_proof", "arguments": {"text": "spoke to Ramesh"}}],
        )
        # And the ledger still gets the row. This is the half that was lost
        # silently even where the raise did not land, and it was lost on
        # precisely the expensive turns — see #261 before quoting any total.
        self.assertEqual(recorded["usage"]["total_tokens"], 1500)


class ModelSpendLedgerTests(TestCase):
    """Every model call lands in the database with what it spent and who spent
    it — the question that had no answer before, because the seam wrote its
    token counts as span attributes that a default deploy discards.

    The rule underneath all of these: accounting may never cost a builder
    their turn. Several tests below break the ledger on purpose and assert the
    call still returns.
    """

    def setUp(self):
        from .. import llm

        llm.clear_actor()
        self.addCleanup(llm.clear_actor)

    def _complete(self, usage, model=None):
        from .. import llm

        with (
            mock.patch("coach.llm.tracer.start_span", return_value=mock.Mock()),
            mock.patch("coach.llm.litellm.completion", return_value=_ok_response(usage)),
        ):
            return llm.complete("system", "user", model=model)

    def test_a_call_is_written_down(self):
        from ..models import ModelCall

        self._complete(_tokens(1200, 80, 1280))
        row = ModelCall.objects.get()
        self.assertEqual(row.prompt_tokens, 1200)
        self.assertEqual(row.completion_tokens, 80)
        self.assertEqual(row.total_tokens, 1280)
        self.assertEqual(row.kind, ModelCall.Kind.COMPLETION)
        self.assertEqual(row.model, settings.LLM_MODEL)

    def test_the_row_holds_the_model_that_was_actually_called(self):
        """Not settings.LLM_MODEL read back later. The setting is what the NEXT
        call will use, and a ledger that rewrites its history the day the model
        is switched cannot answer the one comparison it exists for."""
        from ..models import ModelCall

        self._complete(_tokens(10, 5, 15), model="anthropic/claude-sonnet-5")
        self.assertEqual(ModelCall.objects.get().model, "anthropic/claude-sonnet-5")

    def test_a_priced_model_gets_a_cost(self):
        from ..models import ModelCall

        self._complete(_tokens(1000, 500, 1500), model="openai/gpt-5.4-mini")
        self.assertGreater(ModelCall.objects.get().cost_usd, 0)

    def test_an_unpriced_model_still_gets_a_row(self):
        """litellm raises on a model it has no price for. The tokens are still
        a fact, and a zero written into the cost column would be a lie that
        sums silently into a total somebody trusts."""
        from ..models import ModelCall

        self._complete(_tokens(10, 5, 15), model="openai/not-a-real-model-at-all")
        row = ModelCall.objects.get()
        self.assertIsNone(row.cost_usd)
        self.assertEqual(row.total_tokens, 15)

    def test_a_call_that_reported_nothing_writes_nothing(self):
        """Absent usage is not zero usage. A row of zeros is indistinguishable
        from a call that genuinely cost nothing."""
        from ..models import ModelCall

        self.assertEqual(self._complete(None), "ok")
        self.assertEqual(ModelCall.objects.count(), 0)

    def test_a_stream_writes_exactly_one_row(self):
        """_note_usage is called on EVERY chunk, so the obvious implementation
        writes a row per chunk. The usage arrives once, on a final chunk of its
        own, and the ledger row is booked once when the call closes."""
        from .. import llm
        from ..models import ModelCall

        spoken = mock.Mock(
            choices=[mock.Mock(delta=mock.Mock(content="hi", tool_calls=None))],
            usage=None,
        )
        final = mock.Mock(choices=[], usage=_tokens(5, 2, 7))
        with (
            mock.patch("coach.llm.tracer.start_span", return_value=mock.Mock()),
            mock.patch(
                "coach.llm.litellm.completion", return_value=iter([spoken, final])
            ),
        ):
            list(llm.stream_chat("system", []))
        row = ModelCall.objects.get()
        self.assertEqual(row.kind, ModelCall.Kind.CHAT)
        self.assertEqual(row.total_tokens, 7)

    def test_a_call_that_died_still_books_what_it_had_already_spent(self):
        """The money left the account whether or not the stream finished, and
        a failure part-way is exactly the case worth watching."""
        from .. import llm
        from ..models import ModelCall

        final = mock.Mock(choices=[], usage=_tokens(9, 1, 10))

        def chunks():
            yield final
            raise RuntimeError("provider hung up")

        with (
            mock.patch("coach.llm.tracer.start_span", return_value=mock.Mock()),
            mock.patch("coach.llm.litellm.completion", return_value=chunks()),
            self.assertRaises(RuntimeError),
        ):
            list(llm.stream_chat("system", []))
        self.assertEqual(ModelCall.objects.get().total_tokens, 10)

    def test_a_broken_ledger_does_not_break_the_turn(self):
        """The seam is built so a provider wobble costs a verdict and not the
        app. An accounting row that cannot insert must not become the outage
        accounting was added to prevent."""
        from ..models import ModelCall

        with mock.patch(
            "coach.models.ModelCall.objects.create",
            side_effect=RuntimeError("database gone"),
        ):
            self.assertEqual(self._complete(_tokens(1, 1, 2)), "ok")
        self.assertEqual(ModelCall.objects.count(), 0)

    def test_a_refused_call_books_nothing(self):
        """The breaker refuses before reaching a provider, so nothing was
        spent. A row here would inflate the total with calls never made."""
        from .. import llm
        from ..models import ModelCall

        with mock.patch("coach.llm._breaker_is_open", return_value=True):
            with self.assertRaises(llm.LlmUnavailable):
                llm.complete("system", "user")
        self.assertEqual(ModelCall.objects.count(), 0)

    def test_the_kinds_the_seam_uses_are_the_kinds_the_model_stores(self):
        """spend names them without importing the ORM, so only this stops the
        two drifting — and a kind that is not a valid choice fails on write,
        in production, at the moment somebody wanted the number."""
        from .. import spend
        from ..models import ModelCall

        self.assertEqual(
            {spend.KIND_CHAT, spend.KIND_COMPLETION, spend.KIND_VISION},
            set(ModelCall.Kind.values),
        )

    def test_the_sources_the_seam_names_are_the_sources_the_model_stores(self):
        """Same trap as the kinds, one column over — and worse here, because
        `choices` are not enforced on write: a name that drifted would insert
        happily and leave a pointer nothing can filter on."""
        from .. import spend
        from ..models import ModelCall

        self.assertEqual(set(spend.SOURCES), set(ModelCall.Source.values))

    def test_the_ledger_has_no_default_ordering(self):
        """Meta.ordering joins the GROUP BY on .values(), which would split a
        per-user total into one row per call — on the one table in this project
        whose whole purpose is being aggregated."""
        from ..models import ModelCall

        self.assertFalse(ModelCall._meta.ordering)


class ModelSpendAttributionTests(APITestCase):
    """Whose turn paid for it.

    The trap this exists to catch: authentication here is a DRF class and runs
    INSIDE the view, so at middleware time request.user is AnonymousUser on
    every API request. Reading the id there books every row to nobody — and
    the feature ships green having recorded nothing.
    """

    def setUp(self):
        from .. import llm

        llm.clear_actor()
        self.addCleanup(llm.clear_actor)
        self.user = get_user_model().objects.create_user(
            username="spender", email="spender@example.com", password="pw"
        )

    def test_a_signed_in_builders_call_is_booked_to_them(self):
        from .. import llm
        from ..models import ModelCall

        request = mock.Mock()
        request.user = self.user
        llm.set_actor(request)
        with (
            mock.patch("coach.llm.tracer.start_span", return_value=mock.Mock()),
            mock.patch(
                "coach.llm.litellm.completion",
                return_value=_ok_response(_tokens(3, 1, 4)),
            ),
        ):
            llm.complete("system", "user")
        self.assertEqual(ModelCall.objects.get().user, self.user)

    def test_an_anonymous_request_is_booked_to_nobody(self):
        from django.contrib.auth.models import AnonymousUser

        from .. import llm
        from ..models import ModelCall

        request = mock.Mock()
        request.user = AnonymousUser()
        llm.set_actor(request)
        with (
            mock.patch("coach.llm.tracer.start_span", return_value=mock.Mock()),
            mock.patch(
                "coach.llm.litellm.completion",
                return_value=_ok_response(_tokens(3, 1, 4)),
            ),
        ):
            llm.complete("system", "user")
        self.assertIsNone(ModelCall.objects.get().user)

    def test_a_payer_who_no_longer_exists_books_to_nobody(self):
        """The one route by which accounting could cost a builder their turn.

        `_actor_request` holds a request for the life of the thread — it cannot
        be cleared on the way out or a streamed turn would lose attribution
        mid-flight — so it can name a user id that has since gone. A dangling
        foreign key is checked at COMMIT, not at INSERT, so the create returns
        happily, spend.record's own `except` never fires, and the IntegrityError
        lands on the way out of the builder's request and rolls it back.

        Found by the suite rather than by reading: two accounting tests began
        erroring only when run after a test whose user had been rolled away.
        """
        from .. import llm
        from ..models import ModelCall

        ghost = get_user_model().objects.create_user(
            username="ghost", email="ghost@example.com", password="pw"
        )
        request = mock.Mock()
        request.user = ghost
        llm.set_actor(request)
        ghost.delete()

        with (
            mock.patch("coach.llm.tracer.start_span", return_value=mock.Mock()),
            mock.patch(
                "coach.llm.litellm.completion",
                return_value=_ok_response(_tokens(3, 1, 4)),
            ),
        ):
            self.assertEqual(llm.complete("system", "user"), "ok")

        row = ModelCall.objects.get()
        self.assertIsNone(row.user_id)
        # The money was still spent, so the operator's total must still hold it.
        self.assertEqual(row.total_tokens, 4)

    def test_no_request_at_all_still_records_the_spend(self):
        """The nudge cron, a management command and a shell all reach the seam
        with nobody behind them. That spend is the operator's own."""
        from .. import llm
        from ..models import ModelCall

        with (
            mock.patch("coach.llm.tracer.start_span", return_value=mock.Mock()),
            mock.patch(
                "coach.llm.litellm.completion",
                return_value=_ok_response(_tokens(3, 1, 4)),
            ),
        ):
            llm.complete("system", "user")
        row = ModelCall.objects.get()
        self.assertIsNone(row.user)
        self.assertEqual(row.total_tokens, 4)

    def test_the_middleware_hands_over_the_request_not_an_id(self):
        """If it resolved the id itself it would resolve AnonymousUser, since
        DRF has not authenticated yet at that point in the stack."""
        from django.test import RequestFactory

        from .. import llm
        from ..middleware import LlmBudgetMiddleware

        seen = {}

        def view(request):
            seen["actor"] = llm._actor_request.get()
            return mock.Mock()

        LlmBudgetMiddleware(view)(RequestFactory().get("/"))
        self.assertIsNotNone(seen["actor"])
        self.assertEqual(seen["actor"].path, "/")


class ModelSpendCauseTests(APITestCase):
    """Which turn caused it.

    `kind` says what the seam did and `user` says whose turn it was; neither
    says which row. The pointer is a table name and an id rather than a foreign
    key, so nothing in the database checks it — which makes these tests the
    only thing standing between a correct pointer and a plausible one.
    """

    def setUp(self):
        from .. import llm

        cache.clear()
        llm.clear_actor()
        llm.clear_source()
        self.addCleanup(llm.clear_actor)
        self.addCleanup(llm.clear_source)

    def _complete(self, content="ok"):
        """One real trip through the seam, with only the provider stubbed."""
        from .. import llm

        message = mock.Mock()
        message.content = content
        response = mock.Mock(
            choices=[mock.Mock(message=message)], usage=_tokens(3, 1, 4)
        )
        with (
            mock.patch("coach.llm.tracer.start_span", return_value=mock.Mock()),
            mock.patch("coach.llm.litellm.completion", return_value=response),
        ):
            return llm.complete("system", "user")

    # --- the null case, which is a real state --------------------------------

    def test_a_call_with_nothing_behind_it_still_writes_a_row(self):
        """The nudge cron, a management command and a shell reach the seam with
        no request and no causing row. That spend is the operator's own and
        still counts, so the row is written and the pointer is null — pinned
        rather than assumed, because a null is also what a bug looks like."""
        from ..models import ModelCall

        self.assertEqual(self._complete(), "ok")
        row = ModelCall.objects.get()
        self.assertIsNone(row.source)
        self.assertIsNone(row.source_id)
        self.assertIsNone(row.user_id)
        # The money was still spent, so the operator's total must still hold it.
        self.assertEqual(row.total_tokens, 4)

    # --- the pointer itself --------------------------------------------------

    def test_a_call_inside_a_turn_names_the_row_that_caused_it(self):
        from .. import llm
        from ..models import ModelCall

        with llm.attributing(ModelCall.Source.CHECKIN, 7):
            self._complete()
        row = ModelCall.objects.get()
        self.assertEqual(row.source, ModelCall.Source.CHECKIN)
        self.assertEqual(row.source_id, 7)

    def test_the_pointer_does_not_outlive_the_turn(self):
        """The reason this is scoped where the actor is not. A stale actor is
        at worst the wrong user; a stale source is a lie about causation, and
        it looks exactly like a correct answer."""
        from .. import llm
        from ..models import ModelCall

        with llm.attributing(ModelCall.Source.MESSAGE, 3):
            self._complete()
        self._complete()
        after = ModelCall.objects.order_by("id").last()
        self.assertIsNone(after.source)
        self.assertIsNone(after.source_id)

    def test_a_failed_turn_still_lets_go_of_its_pointer(self):
        """`finally`, not the end of the block: a judge call that raises must
        not leave the next call on this thread charged to its check-in."""
        from .. import llm
        from ..models import ModelCall

        with self.assertRaises(RuntimeError):
            with llm.attributing(ModelCall.Source.CHECKIN, 11):
                raise RuntimeError("the provider hung up")
        self._complete()
        self.assertIsNone(ModelCall.objects.get().source)

    # --- what an unreadable pointer costs, and what it must not --------------

    def test_a_source_the_ledger_does_not_know_costs_the_pointer_not_the_row(self):
        """`choices` are not enforced on write, so a drifted name would insert
        and leave a column nothing can filter on. It is dropped instead — and
        the row, which is the part that cost money, is still written."""
        from .. import llm
        from ..models import ModelCall

        with llm.attributing("PROOF_ATTEMPT", 4):
            self.assertEqual(self._complete(), "ok")
        row = ModelCall.objects.get()
        self.assertIsNone(row.source)
        self.assertIsNone(row.source_id)
        self.assertEqual(row.total_tokens, 4)

    def test_half_a_pointer_is_no_pointer(self):
        """An id with no table is unreadable and a table with no id names
        nothing, so either both survive or neither does."""
        from .. import llm
        from ..models import ModelCall

        with llm.attributing(ModelCall.Source.MESSAGE, None):
            self._complete()
        row = ModelCall.objects.get()
        self.assertIsNone(row.source)
        self.assertIsNone(row.source_id)

    def test_an_impossible_id_does_not_become_an_exception_on_a_turn(self):
        """`source_id` is a PositiveIntegerField, so a negative one would raise
        on write — and spend.record is built around never being the reason a
        turn fails. Checked before the insert rather than caught after it, so
        the row survives with a null pointer instead of being lost with it."""
        from .. import llm
        from ..models import ModelCall

        with llm.attributing(ModelCall.Source.GOAL, -1):
            self.assertEqual(self._complete(), "ok")
        row = ModelCall.objects.get()
        self.assertIsNone(row.source)
        self.assertEqual(row.total_tokens, 4)

    # --- the call sites carrying the questions the ledger was built for ------

    def test_a_chat_turns_spend_points_at_the_message(self):
        """The whole point of the contextvar: the stream is consumed after
        every middleware has returned, so a pointer handed in as an argument
        would have to survive a scope that has already closed."""
        from ..models import ModelCall

        user = make_user("chatter")
        self.client.force_authenticate(user)
        Goal.objects.create(user=user, title="Tiffin app")

        spoken = mock.Mock(
            choices=[
                mock.Mock(delta=mock.Mock(content="Kaam dikhao.", tool_calls=None))
            ],
            usage=None,
        )
        final = mock.Mock(choices=[], usage=_tokens(120, 8, 128))
        with (
            mock.patch("coach.llm.tracer.start_span", return_value=mock.Mock()),
            mock.patch(
                "coach.llm.litellm.completion", return_value=iter([spoken, final])
            ),
        ):
            response = self.client.post(
                "/api/coach/chat/", {"content": "which stack?"}
            )
            b"".join(response.streaming_content)

        turn = Message.objects.get(role=Message.Role.USER)
        row = ModelCall.objects.get()
        self.assertEqual(row.kind, ModelCall.Kind.CHAT)
        self.assertEqual(row.source, ModelCall.Source.MESSAGE)
        self.assertEqual(row.source_id, turn.id)
        self.assertEqual(row.user_id, user.id)

    def test_a_judge_calls_spend_points_at_the_checkin(self):
        """The judge calls carry the large prompts, and they are exactly the
        ones a foreign key to Message could never have seen."""
        from ..models import ModelCall

        user = make_user("judged")
        self.client.force_authenticate(user)
        goal = Goal.objects.create(user=user, title="Tiffin app")
        checkin = CheckIn.objects.create(
            goal=goal,
            date=date.today(),
            phase=goal.phase,
            am_declaration="Talk to three canteen owners.",
        )
        message = mock.Mock()
        message.content = (
            '{"fit": "on_phase", "reaction": "Good.", "proof_ask": "Names."}'
        )
        with (
            mock.patch("coach.llm.tracer.start_span", return_value=mock.Mock()),
            mock.patch(
                "coach.llm.litellm.completion",
                return_value=mock.Mock(
                    choices=[mock.Mock(message=message)], usage=_tokens(900, 40, 940)
                ),
            ),
        ):
            response = self.client.post(f"/api/coach/checkins/{checkin.pk}/judge/")

        self.assertEqual(response.status_code, 200)
        row = ModelCall.objects.get()
        self.assertEqual(row.source, ModelCall.Source.CHECKIN)
        self.assertEqual(row.source_id, checkin.id)
        self.assertEqual(row.user_id, user.id)
