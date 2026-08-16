from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user: username login, unique email, how the coach talks.

    Declared before any real user data exists so AUTH_USER_MODEL never has
    to change mid-project (Django makes that switch very painful later).

    There used to be a `tone` here, ENGLISH or HINGLISH, and it is gone rather
    than left nullable on purpose. Its only other value was HINGLISH, so a
    dead column would have kept the language in the schema, the admin filter
    and the enum — advertising a choice the product had stopped offering, which
    is the defect #268 was about, one layer down. English-only is the policy;
    if Hinglish returns it returns voiced across both rooms and tested at both
    prompt sizes, and it can bring its own column with it.
    """

    class Mode(models.TextChoices):
        """Which side of the table Masterji sits on — the builder's setting,
        not the model's guess.

        COACH is the product: one task, proof tonight, the gate. THINKING is
        for the part of the work that comes before there is anything to
        declare — the builder asks to think it through, and Masterji answers
        with questions and options instead of assignments. Neither one moves
        the gate: gates.py doesn't read this field and never will, which is
        what stops a thinking partner from becoming a way around the door.
        """

        COACH = "COACH", "Coach"
        THINKING = "THINKING", "Thinking partner"

    email = models.EmailField(unique=True)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.COACH)

    # createsuperuser prompts for these in addition to username/password
    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = "user"

    def __str__(self):
        return self.username


class Impersonation(models.Model):
    """One time an operator looked at a builder's account through the app.

    Written by `accounts.admin.MasterjiUserAdmin.impersonate_view` before the
    cookie is handed over, so the record exists whether or not the session is
    ever used. There is no "ended" column and there could not be an honest
    one: the token is stateless, nothing reports its use back here, and a
    field that only ever said "expires_at" while pretending to say "ended"
    would be worse than the gap. What can be known is written down — who,
    whom, when it started, and when it stops working.

    NOT a `SoftDeleteModel`, and that is the difference that matters rather
    than an oversight. Every soft-deleting model in this codebase holds
    something the builder did, so `erasure._descend` stamps it when they ask
    to be gone. This holds something the OPERATOR did, and an account erasure
    is not a reason for the record of who read it to disappear. It survives,
    pointing at a user row whose identity `erase` has already scrubbed — so
    what is left says an operator viewed account 41 on a date, and nothing
    about who account 41 was, which is the correct amount to keep.
    """

    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="impersonations_started",
    )
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="impersonations_received",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    # Stamped from the token's own lifetime rather than recomputed on read, so
    # this row keeps saying what that session's expiry actually was even after
    # IMPERSONATION_LIFETIME_S is changed.
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "impersonation"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.operator} as {self.target} at {self.started_at:%Y-%m-%d %H:%M}"


class PushSubscription(models.Model):
    """One browser that has agreed to be nudged when tonight's proof is owed.

    A row is created by the browser itself: `pushManager.subscribe()` returns
    an endpoint and two keys, and those three strings ARE the permission to
    push to that device. There is nothing else to store and nothing here that
    a person typed.

    Why this lives in `accounts` and not in `coach`: it is a property of the
    person, not of the goal they happen to be running. A builder who retires
    one idea and starts another keeps their notifications, and a row that
    hung off `Goal` would have to be re-granted on the next idea — which
    means asking for notification permission again, which is a thing browsers
    let you spend once.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    # The push service's URL for this device. Unique because it IS the
    # device's identity — re-subscribing the same browser returns the same
    # endpoint, so an upsert on this field is what stops a builder who opens
    # the app on Chrome twice from collecting two rows and two buzzes.
    #
    # TextField rather than a bounded CharField: FCM's are around 200
    # characters today and nothing in the spec bounds them, so a max_length
    # would be a number somebody guessed that later truncates a working
    # subscription into a broken one.
    endpoint = models.TextField(unique=True)
    # The device's own encryption keys. The payload is encrypted to these
    # before it leaves this server (RFC 8291) — which is what makes it safe to
    # put the builder's own task text in a notification that travels through
    # Google's or Mozilla's infrastructure to get there.
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)

    # The IANA zone the browser was in when it subscribed, e.g.
    # "Asia/Kolkata". This is the one genuinely new fact in this model and it
    # is worth being honest about why it has to exist.
    #
    # Nothing else in this product stores a timezone. It never needed one:
    # every request carries the client's own local date and the server reads
    # it (coach.views._client_day), so "today" has always been the browser's
    # to define. A nudge has no request. It is the one thing this app does
    # that starts on the server, so the server has to know what time it is
    # where the builder is, or "after five in the evening" means "after five
    # in the evening in UTC" — 22:30 in India, which is the middle of the
    # night for exactly the users this is for.
    #
    # The zone NAME rather than a stored UTC offset, because an offset goes
    # stale: a builder in London who subscribed in January would be nudged an
    # hour early all summer. ZoneInfo resolves the name against tzdata every
    # time, so DST is somebody else's problem.
    #
    # Captured from the browser at subscribe time and refreshed on every
    # re-subscribe, which is what makes a builder who moves countries right
    # within a day or two rather than never.
    timezone_name = models.CharField(max_length=64, default="UTC")

    # The builder's LOCAL date the last nudge went out for — the whole of
    # "one nudge a day". Their local date, not the server's, because the day
    # this is rationing is the builder's evening.
    #
    # Null until the first one. Stamped on every one of a user's rows at once
    # (see coach.nudges.send_due), so two devices are one nudge delivered
    # twice rather than two nudges.
    last_nudged_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "push subscription"

    def __str__(self):
        return f"{self.user} ({self.timezone_name})"

    def zone(self) -> ZoneInfo:
        """The builder's clock, with UTC as the answer to a name this
        machine cannot resolve.

        The name arrives from a browser and is checked on the way in, so a
        bad one should be impossible — but tzdata is a moving target and a
        zone that was valid when it was stored can stop being valid on a
        later image. Falling back beats raising: the cost of UTC is a nudge
        at the wrong hour, and the cost of an exception here is the hourly
        tick dying on one row and nobody else getting nudged either.
        """
        try:
            return ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC")
