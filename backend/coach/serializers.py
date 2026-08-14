from django.utils import timezone
from rest_framework import serializers

from . import gates, storage
from .models import (
    ChangelogEntry,
    CheckIn,
    Goal,
    GoalRetirement,
    Message,
    PhaseTransition,
    ProofAttempt,
    WorkshopMessage,
)

# How long a hand-written brief may be. Generous next to the title's 200 — this
# is a paragraph about a problem, not a headline — and short enough that the
# block it lands in stays a paragraph in every prompt that carries it. An
# accepted proof is not measured against it: that text cleared the bar and is
# the record, and truncating it here would make the goal disagree with the row
# it came from.
BRIEF_CHARS = 2000


class GoalSerializer(serializers.ModelSerializer):
    # Whether the wording is still the builder's to sharpen. The same count the
    # view checks before allowing it (gates.accepted_proofs_total), sent so the
    # dashboard offers the control exactly while it would be accepted — an edit
    # affordance that appears and then 409s is worse than one that was never
    # there.
    title_locked = serializers.SerializerMethodField()

    class Meta:
        model = Goal
        fields = [
            "id",
            "title",
            "brief",
            "considered",
            "phase",
            "status",
            "phase_entered_at",
            "created_at",
            "title_locked",
            # The goal this one came out of, read-only here and set by the view:
            # it is a claim about another row, and whose row it is and whether
            # it is closed are not a client's to assert.
            "pivoted_from",
        ]
        # Everything except the title and the brief. `phase` and `status` being
        # read-only here is what stops the update endpoint from being a road
        # around the gate — a PATCH may reword a goal and may never advance one.
        read_only_fields = [
            "id",
            # What the room parked is a record of what the builder was
            # choosing between, not a list they may edit afterwards: the
            # workshop is closed and rewriting its pile would rewrite the
            # question this goal was the answer to.
            "considered",
            "phase",
            "status",
            "phase_entered_at",
            "created_at",
            "title_locked",
            "pivoted_from",
        ]

    def get_title_locked(self, obj: Goal) -> bool:
        return gates.accepted_proofs_total(obj) > 0

    def validate_brief(self, value):
        """The brief as the four documented keys, never as arbitrary JSON.

        A JSONField on a writable serializer accepts whatever the client sends,
        and this one is read into a prompt — so the shape is rebuilt here rather
        than trusted. `text` is the only thing a client may set: `parts` is what
        the gate saw and is not a client's to assert, and `source`/`written_at`
        are stamped by the server that did the writing.
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError("Expected an object.")
        text = " ".join(str(value.get("text") or "").split())
        if not text:
            raise serializers.ValidationError("A brief needs text.")
        if len(text) > BRIEF_CHARS:
            raise serializers.ValidationError(
                f"Keep it under {BRIEF_CHARS} characters."
            )
        return {
            "text": text,
            # A hand-written brief makes no claim about the bar. The gate has
            # not seen it, so it satisfies nothing until an accepted proof says
            # otherwise, and an empty list is the honest version of that.
            "parts": [],
            "source": "BUILDER",
            "written_at": timezone.now().isoformat(),
        }


def _image_path(kind: str, pk: int, key: str) -> str:
    """Where to ask for a proof image — this app's address for it, not R2's.

    It used to be the signed URL itself, and signing is an S3 operation per
    row. `StateView` serializes CHECKIN_HISTORY rows with their attempts
    prefetched, so the dashboard — the most-loaded authenticated endpoint in
    the product, and the screen every builder opens first — paid for up to
    ninety-odd signatures inline, to render a list that shows no images at
    all. The image is behind opening a day.

    Invisible until now only because R2 is optional: an unconfigured deploy
    skips the whole branch. That makes it a latency cliff that arrives on the
    day storage is switched on in production, and reads as "the app got slow"
    rather than as the configuration change it was.

    So the row carries a path and views.ProofImageView signs when the browser
    actually asks for the bytes. Three things fall out of that, all of them
    improvements on what was here:

    - The payload holds no credentials of any kind, signed or otherwise.
    - The link cannot expire before it is used. A URL signed at dashboard load
      was good for storage.VIEW_URL_TTL — five minutes — and a builder who
      opened a day after that got a broken image on the record screen.
    - The bucket is still private and the signature is still short-lived. What
      changed is when it is minted, not what it protects.

    An empty string still means "no image here", which is what every caller
    already checks for.
    """
    if not key or not storage.is_configured():
        return ""
    return f"/api/coach/{kind}/{pk}/image/"


class ProofAttemptSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProofAttempt
        fields = ["id", "text", "url", "image_url", "reaction", "created_at"]
        read_only_fields = fields

    def get_image_url(self, obj: ProofAttempt) -> str:
        return _image_path("attempts", obj.pk, obj.image_key)


class CheckInSerializer(serializers.ModelSerializer):
    # The pushed-back tries behind this check-in's current proof, oldest
    # first. Callers serializing many rows should prefetch "attempts".
    attempts = ProofAttemptSerializer(many=True, read_only=True)
    # This app's own address for the image, not a signed one — see
    # _image_path. The signing happens when the image is actually opened.
    proof_image_url = serializers.SerializerMethodField()

    class Meta:
        model = CheckIn
        fields = [
            "id",
            "date",
            "phase",
            "am_declaration",
            "declaration_fit",
            "declaration_reaction",
            "proof_ask",
            "proof_offer",
            "proof_missing",
            "pm_proof_text",
            "proof_url",
            "proof_image_url",
            "proof_status",
            "coach_reaction",
            "attempts",
        ]
        read_only_fields = fields

    def get_proof_image_url(self, obj: CheckIn) -> str:
        return _image_path("checkins", obj.pk, obj.proof_image_key)


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        # `phase` has been stamped on every row since the model had the field,
        # and was never sent. The client needs it to tell "this builder has
        # said nothing in the phase they are in now" from "this log is empty",
        # which is what decides whether the phase's opening questions are worth
        # offering — see the openers in app/Masterji.tsx.
        # `kind` rides along for the same reason: it is what tells a SYSTEM row
        # that is a failed turn from one that is the week read back, and the
        # retry button belongs to only one of them.
        fields = ["id", "role", "kind", "content", "phase", "created_at"]
        read_only_fields = fields


class WorkshopMessageSerializer(serializers.ModelSerializer):
    """A workshop turn. No `phase` field, unlike MessageSerializer, because the
    room exists precisely where there is no phase to stamp."""

    class Meta:
        model = WorkshopMessage
        fields = ["id", "role", "content", "created_at"]
        read_only_fields = fields


class RetirementSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="goal.title", read_only=True)
    # Computed from earned proofs, never stored and never client-settable, so
    # it can't drift or be forged into a flattering label.
    reads_as = serializers.SerializerMethodField()

    class Meta:
        model = GoalRetirement
        fields = [
            "id",
            "goal",  # the closed goal's id, for fetching its day-by-day record
            "title",
            "outcome",
            "reads_as",
            "reason",
            "phase_reached",
            "accepted_proofs",
            "contact_proofs",
            "days_active",
            "best_streak",
            "coach_reaction",
            # Only ever the owner's: this serializer feeds the archive on their
            # own dashboard, and the public page reads a different one that has
            # never heard of an account. Null means private, which is where
            # every record starts and stays until they press the switch.
            "share_slug",
            "created_at",
        ]
        read_only_fields = fields

    def get_reads_as(self, obj) -> str:
        return gates.reads_as(obj.goal, obj.outcome)


class PhaseTransitionSerializer(serializers.ModelSerializer):
    """Phase boundaries — the frontend derives each phase's date window
    from these plus the goal's created_at, to power the stepper drill-in.

    `intent` rides along because the drill-in is the one place a builder reads a
    phase back as a whole: what they said it would produce belongs next to what
    it actually did. Read-only here — it is written by PhaseIntentView, which is
    the one place that knows a line may only describe the open phase."""

    class Meta:
        model = PhaseTransition
        fields = ["from_phase", "to_phase", "intent", "created_at"]
        read_only_fields = fields


class ChangelogEntrySerializer(serializers.ModelSerializer):
    """Read-only, and public: this is the one payload here that isn't scoped
    to a user, so it carries nothing but the entry itself."""

    class Meta:
        model = ChangelogEntry
        fields = ["id", "shipped_on", "kind", "title", "body"]
        read_only_fields = fields
