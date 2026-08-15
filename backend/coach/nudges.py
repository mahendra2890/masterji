"""The evening nudge: who is owed one, and how it leaves the building.

The only thing this product does that starts on the server. Everything else
is a reply to a request a builder made, which is why nothing here could be
reused — there is no `request.user` to read, no client-supplied local date
(coach.views._client_day), and no browser awake to be told anything.

**Eligibility is arithmetic over rows that already exist.** A proof is owed
when `views._open_checkin` finds a cycle still open on the builder's local
date, and their local evening has arrived. No new state decides who gets a
nudge, no model is asked, and `gates.py` is not touched — the nudge cannot
bank a day, refuse one, or move a phase. It buzzes a phone and stops.

**The trigger is an hourly tick, and it selects who is due** (#142). Not a
job scheduled at a named hour: free-tier GitHub Actions `schedule:` runs slip
by minutes to hours, so a job set for 21:00 delivers at a random time and
teaches the builder the hour was decorative. Running every hour and asking
"whose evening has started, and who still owes a proof" degrades to "shortly
after", which is a thing that can be said out loud honestly.

That shape is also what lets #96 ride this same tick. #96 landed while this
was being built, so `CheckIn.due_hour` is now on the row — but only its own
half: the hour is a record and a fact in the prompt, and its tests pin that it
changes nothing about what counts. Joining the two is one line here
(`EVENING_FROM` becomes `checkin.due_hour` when the builder named one) and it
is deliberately not in this pull request, because #96 decided on purpose that
the hour is not enforced, and a notification fired at it is exactly the
enforcement that decision declined. That is a product call for whoever makes
it next, not a loose end in this one. **This does NOT build #96.**
"""

import hmac
import json
from dataclasses import dataclass
from datetime import date, datetime

from django.conf import settings
from django.utils import timezone
from loguru import logger
from pywebpush import WebPushException, webpush
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import PushSubscription
from accounts.throttling import TrustedIdentThrottle

from . import prompts
from .models import CheckIn
from .views import _active_goal, _open_checkin

# The hour a builder's evening starts, local to them.
#
# The same 17 as `EVENING_FROM` in app/Masterji.tsx, and the duplication is
# real: there is no config this repo shares between TypeScript and Python, so
# the number is written twice and the two copies have to be moved together.
# They are the same fact — the hour the evening half of the Today card unfolds
# is the hour it is fair to ask about the box it unfolds — and a nudge that
# fired before the card opened would point at something the app is still
# hiding.
#
# Erring early costs a builder a notification an hour before they meant to
# work. Erring late costs them the proof. Masterji.tsx made that trade at 17
# and this makes the same one.
EVENING_FROM = 17

# What the browser is told to open when the notification is tapped. The
# dashboard, because that is where the box is — the notification's whole job
# is to be one tap from the thing it is about.
NUDGE_URL = "/"


def _configured() -> bool:
    """Whether this deployment can actually send. Three unset variables is
    the default, and it means the feature is off end to end rather than
    half-wired — see the block in settings.py."""
    return bool(
        settings.VAPID_PUBLIC_KEY
        and settings.VAPID_PRIVATE_KEY
        and settings.VAPID_CONTACT
    )


# --- who is due -------------------------------------------------------------


@dataclass(frozen=True)
class Due:
    """One builder owed tonight's nudge, and every device to send it to."""

    user: object
    # The builder's LOCAL date. Every date in this module is theirs, never the
    # server's — the server's is UTC, and a UTC evening is the middle of the
    # night in the timezone this product's users are actually in.
    day: date
    checkin: CheckIn
    subscriptions: list[PushSubscription]


def owes_proof(user, day: date) -> CheckIn | None:
    """The cycle this builder declared on `day` and has not proved.

    The whole eligibility rule, and it is one call into the same helper the
    dashboard and ProveView read. A pushed-back proof still counts as owed,
    because `_open_checkin` says so — that is the evening where a nudge is
    worth the most, not the one where it is a duplicate.

    Deliberately NOT "they declared nothing today". A day with no declaration
    has no proof owed on it, so there is nothing here to hold them to, and a
    notification that says "you didn't start" is the scolding this product
    refuses. `_open_checkin` non-empty is the bar and nothing else is.

    No carry-over (`views._carried_over`), which the dashboard does read. That
    window exists so a proof typed at 00:30 lands on the evening it belongs
    to; it is about a builder who is at their desk. Nudging on it would buzz
    somebody after midnight about a day that is over.
    """
    goal = _active_goal(user)
    if goal is None:
        return None
    return _open_checkin(goal, day)


def _local(subscription: PushSubscription, now: datetime) -> datetime:
    return now.astimezone(subscription.zone())


def due_now(now: datetime | None = None) -> list[Due]:
    """Everyone this tick should nudge.

    Grouped by builder rather than by device, because "one nudge a day" is a
    promise to a person. A builder with a phone and a laptop gets one nudge
    delivered to both, which is how every notification anyone already has
    behaves — not two nudges, and not a coin flip about which device wins.

    Which device's clock decides the evening: the first one, by row order,
    that says the evening has started. The date it reports is then the date
    everything else here is keyed on. This only matters for a builder holding
    devices in different timezones, which is somebody travelling — and for
    them the friendly answer is that the evening starts when their first
    device says it has, not when their slowest one catches up.
    """
    now = now or timezone.now()
    rows = list(
        PushSubscription.objects.select_related("user")
        .filter(user__is_active=True)
        .order_by("id")
    )
    by_user: dict[int, list[PushSubscription]] = {}
    for row in rows:
        by_user.setdefault(row.user_id, []).append(row)

    due: list[Due] = []
    for subscriptions in by_user.values():
        evening = next(
            (s for s in subscriptions if _local(s, now).hour >= EVENING_FROM), None
        )
        if evening is None:
            continue
        day = _local(evening, now).date()
        # One a day, and it is read off the record rather than counted in
        # memory — the tick runs hourly, so from 17:00 to midnight this
        # question gets asked seven more times for the same evening, and the
        # stamp is the only thing between that and seven notifications.
        if any(s.last_nudged_on == day for s in subscriptions):
            continue
        checkin = owes_proof(evening.user, day)
        if checkin is None:
            continue
        due.append(
            Due(
                user=evening.user,
                day=day,
                checkin=checkin,
                subscriptions=subscriptions,
            )
        )
    return due


# --- sending ----------------------------------------------------------------


def _payload(due: Due) -> str:
    return json.dumps(
        {
            "title": prompts.NUDGE_TITLE,
            "body": prompts.nudge_body(due.checkin.am_declaration),
            "url": NUDGE_URL,
        }
    )


def _push(subscription: PushSubscription, payload: str) -> bool:
    """One notification to one device. True if the push service took it.

    Encrypted to the device's own keys before it leaves here (RFC 8291), which
    is what makes it acceptable to put the builder's own words in a message
    that travels through Google's or Mozilla's infrastructure: the push
    service routes an opaque blob and cannot read the task.

    A subscription the push service has retired is deleted rather than
    retried. 404 and 410 mean the browser is gone — the app was uninstalled,
    the site data cleared, the permission revoked — and a row that answers 410
    forever is a row that will answer 410 forever.
    """
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_CONTACT},
            timeout=settings.NUDGE_TIMEOUT_S,
        )
        return True
    except WebPushException as exc:
        code = getattr(exc.response, "status_code", None)
        if code in (404, 410):
            # Read before the delete: `delete()` clears the pk, and a log line
            # that says "subscription None is gone" is a log line nobody can
            # follow up.
            pk = subscription.pk
            subscription.delete()
            logger.info(f"Push subscription {pk} is gone ({code}) — reaped")
        else:
            logger.warning(f"Push to {subscription.pk} failed: {code} {exc}")
        return False
    except Exception as exc:  # noqa: BLE001 — one bad row must not end the tick
        # A DNS failure, a socket timeout, a push service having a bad
        # afternoon. Nobody is waiting on this response and there is no
        # retry: the next tick is in an hour and the stamp below is only
        # written for a builder somebody was actually reached for, so a
        # failed evening is retried by the clock rather than by a queue.
        logger.warning(f"Push to {subscription.pk} raised: {exc!r}")
        return False


def send_due(now: datetime | None = None) -> dict:
    """Run one tick. Returns what happened, for the workflow's log.

    The stamp is written per builder and only when at least one of their
    devices took the message, so an evening where every push failed is tried
    again on the next tick rather than silently counted as delivered. It is
    written to ALL of that builder's rows at once, which is what keeps "one a
    day" a fact about the person after a second device is added.
    """
    if not _configured():
        return {"sent": 0, "builders": 0, "skipped": "not configured"}
    due = due_now(now)
    sent = 0
    reached = 0
    for entry in due:
        payload = _payload(entry)
        delivered = [s for s in entry.subscriptions if _push(s, payload)]
        if not delivered:
            continue
        sent += len(delivered)
        reached += 1
        PushSubscription.objects.filter(
            pk__in=[s.pk for s in entry.subscriptions]
        ).update(last_nudged_on=entry.day)
    logger.info(f"Nudge tick: {reached} builders, {sent} devices, {len(due)} due")
    return {"due": len(due), "builders": reached, "sent": sent}


# --- endpoints --------------------------------------------------------------

# Bounds on what a browser may store here. The endpoint is a URL a push
# service minted and nothing in the spec bounds it; these are generous against
# the ~200 characters real ones run to, and they exist so a bad client cannot
# write a megabyte into a TextField.
ENDPOINT_MAX_CHARS = 2000
KEY_MAX_CHARS = 200


class PushSubscriptionView(APIView):
    """The builder's opt-in, from the browser that will be nudged.

    GET says whether this deployment can push at all and hands over the VAPID
    public key. Served from here rather than baked into the frontend build on
    purpose: the private half lives on Render, and a public half set as a
    Vercel build-time variable is a second copy that can silently drift from
    it — at which point every subscription this app collects is encrypted to a
    key it cannot sign for, and the only symptom is notifications that never
    arrive.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [TrustedIdentThrottle]
    throttle_scope = "push"

    def get(self, request):
        return Response(
            {
                "configured": _configured(),
                "public_key": settings.VAPID_PUBLIC_KEY,
                "evening_from": EVENING_FROM,
            }
        )

    def post(self, request):
        if not _configured():
            return Response(
                {"detail": "Push isn't set up on this deployment."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        data = request.data if hasattr(request.data, "get") else {}
        endpoint = str(data.get("endpoint") or "").strip()
        keys = data.get("keys") if hasattr(data.get("keys"), "get") else {}
        p256dh = str((keys or {}).get("p256dh") or "").strip()
        auth = str((keys or {}).get("auth") or "").strip()
        if (
            not endpoint.startswith("https://")
            or len(endpoint) > ENDPOINT_MAX_CHARS
            or not p256dh
            or not auth
            or len(p256dh) > KEY_MAX_CHARS
            or len(auth) > KEY_MAX_CHARS
        ):
            return Response(
                {"detail": "That isn't a push subscription."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        zone = _clean_zone(data.get("timezone"))

        existing = PushSubscription.objects.filter(endpoint=endpoint).first()
        if existing and existing.user_id != request.user.pk:
            # The same browser, a different person — a shared laptop where
            # somebody else signed in. The row moves, and the stamp is
            # cleared with it, because "already nudged today" was a fact
            # about the builder who left rather than the one sitting here.
            existing.last_nudged_on = None
        subscription = existing or PushSubscription(endpoint=endpoint)
        subscription.user = request.user
        subscription.p256dh = p256dh
        subscription.auth = auth
        # Refreshed on every subscribe, not only on the first: this is how a
        # builder who moved countries starts being nudged in the right
        # evening, and re-subscribing happens on every visit.
        subscription.timezone_name = zone
        subscription.save()
        return Response(
            {"ok": True},
            status=status.HTTP_200_OK if existing else status.HTTP_201_CREATED,
        )

    def delete(self, request):
        """Turn it off. Scoped to this user's own rows, so knowing somebody
        else's endpoint is not a way to unsubscribe them."""
        data = request.data if hasattr(request.data, "get") else {}
        endpoint = str(
            data.get("endpoint") or request.query_params.get("endpoint") or ""
        ).strip()
        rows = PushSubscription.objects.filter(user=request.user)
        # No endpoint means "this account, everywhere" — the honest reading of
        # an off switch pressed by somebody who cannot see their device list.
        if endpoint:
            rows = rows.filter(endpoint=endpoint)
        rows.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _clean_zone(raw) -> str:
    """An IANA name the server can resolve, or UTC.

    Checked against this machine's own tzdata rather than a regex, because
    the thing that matters is whether `ZoneInfo` will accept it in six
    months — a name that only looks right stores fine and then silently
    nudges at the wrong hour forever.
    """
    from zoneinfo import available_timezones

    name = str(raw or "").strip()
    return name if name in available_timezones() else "UTC"


class NudgeRunView(APIView):
    """The one endpoint the hourly workflow calls.

    Authenticated with a shared secret in a header, not a session: the caller
    is a GitHub Actions job with no cookie jar and no account. `X-Nudge-Token`
    rather than `Authorization`, deliberately — simplejwt is the default
    authenticator on this project and would try to parse a bearer token as a
    JWT, so a perfectly good secret would come back 401 for the wrong reason.

    `authentication_classes = []` for the same reason: this view's answer must
    not depend on whatever cookies happened to ride along.

    An unset `NUDGE_TOKEN` refuses. That is the whole security property and it
    is worth stating: "not configured" must never collapse into "no auth
    required", which is exactly what a `compare_digest("", "")` would do.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        expected = settings.NUDGE_TOKEN
        if not expected:
            return Response(
                {"detail": "Nudges aren't set up on this deployment."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        sent = request.headers.get("X-Nudge-Token", "")
        if not hmac.compare_digest(sent, expected):
            return Response(
                {"detail": "No."}, status=status.HTTP_401_UNAUTHORIZED
            )
        return Response(send_due())
