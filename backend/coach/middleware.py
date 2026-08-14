"""Request-scoped plumbing for the model calls.

Separate from llm.py because a Django middleware is a config concern and the
seam is not: llm.py is imported by views, by a shell, and by the tests, none of
which have a request to hang a budget on.
"""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from . import llm


class LlmBudgetMiddleware:
    """Starts this request's wall-clock budget for model calls, and says whose
    turn is paying for them.

    Deliberately does NOT clear it on the way out. The two longest paths in
    the product return a StreamingHttpResponse, whose body is consumed after
    every middleware has already returned — clearing here would take the
    budget away from exactly the requests it exists to bound, and it would do
    it silently, because a stream that loses its deadline simply goes back to
    being unbounded.

    A deadline left behind on the thread is harmless: every request sets its
    own before it can make a call, so a stale value is always overwritten
    before anything reads it. The one thread that could inherit a stale
    deadline is one that never serves a request, and llm.clear_budget is there
    for that case.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        llm.begin_budget()
        # The request itself, NOT request.user.id. Authentication is DRF's
        # CookieJWTAuthentication and runs inside the view, so nobody is
        # signed in yet at this point in the stack — reading an id here would
        # book every row to nobody. llm._current_actor resolves it when the
        # ledger row is actually written, and its comment carries the detail.
        llm.set_actor(request)
        return self.get_response(request)
