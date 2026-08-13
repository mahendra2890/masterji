"""Ceilings on the endpoints that spend money, and the words they refuse in.

Three views call a model: the chat, the proof verdict, and the reading of the
morning's task. Each one is a paid call with no limit on how often it could be
asked for, which makes the LLM budget every honest builder's verdict comes out
of drainable by one scripted account — and this has to exist before ₹99–199/mo
billing makes those economics real rather than theoretical.

Not a coaching limit, and deliberately not in gates.py: a throttle refuses a
REQUEST, never a proof. Nothing here can change what the record holds, what a
phase costs, or whether a day counted. A builder who hits one of these has done
nothing wrong — they are being asked to come back, which is why the refusals are
written rather than left to DRF's arithmetic. The rates live in
settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].
"""

from rest_framework.exceptions import Throttled
from rest_framework.throttling import ScopedRateThrottle

# The one throttle class every paid view uses. Which bucket a view draws from is
# the view's own `throttle_scope` — no subclass per endpoint, because
# ScopedRateThrottle reads that attribute off the view and a subclass carrying
# its own scope would be quietly ignored.
THROTTLES = [ScopedRateThrottle]


class VoicedThrottleMixin:
    """Say the refusal in the product's own register.

    DRF's default is "Request was throttled. Expected available in 3540
    seconds." — true, and the voice of a rate limiter rather than of a coach.
    The wait is kept on the exception so the Retry-After header still goes out;
    only the prose changes, and nothing about the ceiling moves.
    """

    throttle_message = "Too many at once. Come back to it in a bit."

    def throttled(self, request, wait):
        refusal = Throttled(detail=self.throttle_message)
        # Set after construction on purpose: passing `wait` to the constructor
        # appends DRF's seconds-remaining sentence to the message above.
        refusal.wait = wait
        raise refusal
