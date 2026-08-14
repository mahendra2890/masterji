"""One job: give every request a fresh wall-clock budget for model calls.

The budget itself lives in `coach.llm` — see the long note there for why a
provider wobble was able to take the whole app down rather than just the
verdict. This is only the thing that starts the clock, and it is middleware
rather than a lazy initialiser inside `llm` for one reason:

`start.sh` runs gunicorn with `--threads 12`, and a ContextVar lives as long as
its thread. A deadline set lazily on the first model call would be *inherited*
by whichever request that thread served next, so the second builder in a reused
thread would find the budget already spent by the first. Setting it per request
is what makes it a per-request budget rather than a per-thread one.

Cheap enough to sit in front of everything: two attribute writes and a clock
read on requests that never call a model, which is most of them.
"""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from . import llm


class LlmBudgetMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Set on the way in and deliberately NOT cleared on the way out.
        #
        # A streaming response is iterated after this returns — on this thread,
        # in this context — so clearing it here would take the budget away from
        # the chat turn, which is the longest call the product makes and the one
        # that most wants a ceiling. Staleness is already answered by this line
        # being unconditional: the next request through resets the clock before
        # anything it does can reach a model.
        llm.set_deadline(settings.LLM_REQUEST_BUDGET_S)
        return self.get_response(request)
