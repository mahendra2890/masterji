"""What each model call cost, and whose turn caused it.

Separate from llm.py on the same argument middleware.py already makes: the
seam is about reaching a provider, and this is about writing a row. llm.py is
imported by a shell and by tests that have no database intent, so the ORM does
not belong inside it.

The rule this module is built around, and the reason almost everything here is
wrapped in a try: **accounting must never be the reason a builder's turn
fails.** The whole seam is shaped so a provider wobble costs a verdict rather
than the app (#151); an accounting row that cannot insert must not become the
outage that accounting was added to prevent. Every failure here is logged and
swallowed, and the caller is never told — because there is nothing the caller
could usefully do about it in the middle of somebody's sentence.
"""

from decimal import Decimal, InvalidOperation

import litellm
from loguru import logger

# The three shapes of call the seam makes. Named here rather than imported
# from models so llm.py can label a call without pulling the ORM into a module
# that a shell and the tests import for its own sake. `ModelCallKindsTests`
# pins these against ModelCall.Kind, which is what stops the two drifting.
KIND_CHAT = "CHAT"
KIND_COMPLETION = "COMPLETION"
KIND_VISION = "VISION"


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal | None:
    """What those tokens cost on that model, or None if nobody can say.

    None rather than 0 is the whole point. `LLM_MODEL` is a settings string
    and may name a model litellm has no price for — litellm *raises* in that
    case, verified, rather than returning zero — and a zero written into a
    cost column is a lie that sums silently into a total somebody will trust.
    An unpriced call is a real state and it is spelled None.
    """
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except Exception as exc:  # unknown model, or litellm's price map moved
        logger.warning("llm spend: no price for {} ({})", model, exc)
        return None
    try:
        # str() rather than Decimal(float): the floats litellm returns are
        # binary approximations, and feeding one straight to Decimal keeps
        # every bit of that error in a column that gets summed.
        return Decimal(str(prompt_cost)) + Decimal(str(completion_cost))
    except (InvalidOperation, ValueError):
        logger.warning("llm spend: uncomputable price for {}", model)
        return None


def _live_actor(user_id: int | None) -> int | None:
    """`user_id` if that user still exists, otherwise None.

    One indexed primary-key lookup per model call — free beside a call that
    takes seconds and costs money — and it closes the one hole in this module's
    promise that accounting can never cost a builder their turn.

    The promise has a gap without it. `llm._actor_request` holds a request for
    the life of the thread (it cannot be cleared on the way out, or a streamed
    chat turn would lose its attribution mid-flight), so a stale request can
    name a user id that no longer exists. Writing it produces a dangling
    foreign key — and both SQLite and Postgres check that at COMMIT, not at
    INSERT. So `ModelCall.objects.create` returns happily, the `except` below
    never sees anything, and the IntegrityError lands later, on the way out of
    the builder's own request, rolling their turn back. The one failure mode
    this module exists to prevent, arriving by the one route it cannot catch.

    Booking the spend to nobody is the right answer when the payer cannot be
    identified: the money was still spent, and the operator's total stays true.
    """
    if user_id is None:
        return None
    from django.contrib.auth import get_user_model

    try:
        # `_base_manager`, because the question is whether the ROW exists —
        # which is all a foreign key cares about. An erased account keeps its
        # row (erasure overwrites the identity rather than deleting it), and
        # its spend should stay attributed to it; a default manager that
        # learned to hide such rows would silently start orphaning the ledger.
        if get_user_model()._base_manager.filter(pk=user_id).exists():
            return user_id
    except Exception:
        logger.exception("llm spend: could not confirm the payer")
    return None


def record(
    *, kind: str, model: str, usage: dict[str, int], user_id: int | None
) -> None:
    """Persist one model call. Never raises.

    `usage` is what llm._usage_attributes read off the provider — it may be
    empty, and an empty one writes nothing. A call whose usage never arrived
    (a stream that died mid-flight, a provider that does not report) has no
    token count to record, and a row of zeros would be indistinguishable from
    a call that genuinely cost nothing.
    """
    if not usage:
        return
    # Imported here rather than at module scope: llm.py imports this module,
    # and models.py is not safe to import while apps are still loading.
    from .models import ModelCall

    user_id = _live_actor(user_id)
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    try:
        ModelCall.objects.create(
            user_id=user_id,
            kind=kind,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            # Not prompt+completion: providers have been known to disagree
            # with their own arithmetic, and the number they reported is the
            # number worth keeping. Falls back to the sum only when absent.
            total_tokens=usage.get("total_tokens", prompt_tokens + completion_tokens),
            cost_usd=cost_usd(model, prompt_tokens, completion_tokens),
        )
    except Exception:
        logger.exception("llm spend: could not record a {} call on {}", kind, model)
