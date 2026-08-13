"""Masterji's state machine lives in these rows, not in the LLM.

A user has at most ONE active goal (database constraint — the product
thesis is one thing at a time). The goal walks IDEA → VALIDATION → BUILD →
LAUNCH, and every transition is earned with accepted proofs (see gates.py).
Check-ins are the daily declare-AM / prove-PM loop; messages are the chat
transcript. Tenancy rule: views filter by request.user, so foreign ids 404.
"""

from django.conf import settings
from django.db import models

from common.soft_delete import SoftDeleteModel


class Phase(models.TextChoices):
    IDEA = "IDEA", "Idea"
    VALIDATION = "VALIDATION", "Validation"
    BUILD = "BUILD", "Build"
    LAUNCH = "LAUNCH", "Launch"
    # The last one. LAUNCH used to end the ladder, which put the finish line at
    # the moment the post goes out — and the statistic this product opens with
    # is about the stretch that starts there. Retention and the first rupee are
    # still inside the stated altitude (idea → first users); scaling,
    # fundraising and exit talk are not, and the ladder stops here.
    TRACTION = "TRACTION", "Traction"


class Goal(SoftDeleteModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        ABANDONED = "ABANDONED", "Abandoned"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals"
    )
    title = models.CharField(max_length=200)
    phase = models.CharField(max_length=12, choices=Phase.choices, default=Phase.IDEA)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    # Proofs only count toward the gate if earned in the current phase.
    phase_entered_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(SoftDeleteModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="ACTIVE", deleted_at__isnull=True),
                name="one_active_goal_per_user",
            )
        ]

    def __str__(self):
        # Title only — deliberately no phase. This label renders wherever a
        # goal is referenced, including rows written phases ago, and mutable
        # state in it reads as history being rewritten: a message sent during
        # IDEA would show "[VALIDATION]" once the goal moved on. Per-row phase
        # lives on the rows themselves (CheckIn.phase, Message.phase).
        return self.title


class CheckIn(SoftDeleteModel):
    """One declare→prove cycle: the task claimed, and the proof of it.

    Usually one a day (the habit the coach is building), but a builder who
    genuinely does more in a day may run more cycles — real work counts
    when it happens. Only ONE may be open at a time per day, so there is
    always exactly one task on the hook; Masterji does the pacing in
    conversation, not by silently declining to count what you did.
    """

    class ProofStatus(models.TextChoices):
        NONE = "NONE", "No proof yet"
        ACCEPTED = "ACCEPTED", "Accepted"
        PUSHED_BACK = "PUSHED_BACK", "Pushed back"
        # Filed, and nobody has read it — the model was unreachable when it
        # landed. The twin of DeclarationFit.UNJUDGED, and for the same reason:
        # "the model didn't answer" is a real state and must not be spelled as
        # a verdict in either direction.
        #
        # This used to be ACCEPTED. The daily loop is right to survive an
        # outage — a builder's streak must not break because an API flaked —
        # but one decision was doing two jobs, and the second one was the gate.
        # With the model down, "think about the problem" proved by "I thought
        # about it a lot and read some articles" was accepted, banked 1/1
        # toward VALIDATION, and lit "Earned. VALIDATION is yours to open."
        # The phase whose whole job is preventing that opened for exactly it.
        #
        # So the two jobs are split. The day still counts everywhere days are
        # counted — streaks.py reads a declaration and a proof, never a verdict
        # — and the record still shows it. What it does not do is bank a proof
        # toward a phase: gates.py counts ACCEPTED and this is not that. The
        # cycle stays open (views._open_checkin), so filing again once the
        # model is back gets it judged for real.
        UNJUDGED = "UNJUDGED", "Not judged"

    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="checkins")
    date = models.DateField()
    # The phase this day's work belonged to, stamped when the row is created.
    # `date` can't be used to infer it: dates come from the CLIENT's local
    # clock while phase transitions are recorded in server UTC, so around a
    # late-night advance the two disagree about which day it is.
    phase = models.CharField(max_length=12, choices=Phase.choices, blank=True)
    am_declaration = models.TextField(blank=True)
    # Whether this morning's task is the work this phase is actually for.
    # Advisory, never a veto: the builder may do whatever they declared, and
    # a task judged off-phase still earns its proof. UNJUDGED is the honest
    # state when the model was unreachable — not a silent "fine".
    class DeclarationFit(models.TextChoices):
        UNJUDGED = "UNJUDGED", "Not judged"
        ON_PHASE = "ON_PHASE", "On phase"
        OFF_PHASE = "OFF_PHASE", "Off phase"

    declaration_fit = models.CharField(
        max_length=12, choices=DeclarationFit.choices, default=DeclarationFit.UNJUDGED
    )
    declaration_reaction = models.TextField(blank=True)
    # What tonight's proof must show FOR THIS TASK. Falls back to the phase's
    # static ask (guidance.PROOF_HINT) when empty, so the form is never blank.
    proof_ask = models.TextField(blank=True)
    # Tonight's proof as Masterji has it so far, written from work the builder
    # described in conversation (the suggest_proof tool). A RUNNING draft: he
    # rewrites it every time another piece arrives, so it always holds the whole
    # of what the evening has produced. An OFFER, never a record — it puts a
    # filled-in box in front of the builder and they still have to file it.
    # Kept on the row because both later readers need it: the next chat turn
    # reads it as already-given (so nothing in it is ever asked for twice), and
    # the evening's judgement reads it back — a complete draft filed unedited
    # needs no second opinion, and an edited one must not be re-litigated.
    proof_offer = models.TextField(blank=True)
    # What that draft still lacks, one short phrase per piece, semicolon-
    # separated. It is the whole of what Masterji may still ask for tonight,
    # and it is the difference between notes and an offer: empty means the
    # draft clears the phase's bar, and ONLY then may filing it unedited skip
    # the evening's judgement (views._react_to_proof). Notes are a record of
    # what the builder said, never a verdict — a partial draft that gets filed
    # is judged like any other proof.
    proof_missing = models.TextField(blank=True)
    # WHO this evening's proof is about, as a counting key — normalised (folded
    # and whitespace-collapsed) so "Priya " and "priya" are one person, and read
    # by nothing that displays anything. gates.accepted_proofs counts distinct
    # values of it at VALIDATION, which is the phase whose whole point is that
    # more than one person has the problem. Three real conversations with the
    # same hostelmate are three days of real work and one person's word.
    #
    # BLANK IS NOT A FAILURE. An unlabelled proof counts as its own person, the
    # same way a missing screenshot costs the day nothing: the label is the
    # model's contribution and the work is the builder's, so a proof that was
    # accepted on its merits must never be un-banked because the extraction
    # came back empty.
    subject = models.CharField(max_length=120, blank=True)
    # Which parts of the phase's bar (bar.BAR) this evening's evidence actually
    # satisfied — the keys only, never the values, because the values are the
    # proof text and it is already on the row.
    #
    # This is what lets a gate count KINDS rather than rows. BUILD's bar is
    # any-of — a link that loads, OR evidence a real user touched it — so two
    # link evenings could leave BUILD with nobody having touched the thing,
    # which is the one outcome the phase exists to prevent. Written once when
    # the proof is judged, and never rewritten afterwards: same discipline as
    # `phase`, and for the same reason — a banked proof whose label can move is
    # a gate that can be re-argued.
    proof_parts = models.JSONField(default=list, blank=True)
    pm_proof_text = models.TextField(blank=True)
    proof_url = models.URLField(blank=True)
    # Opaque object-storage key for a screenshot backing tonight's proof.
    # Corroboration, never the proof itself: a failed upload must not cost the
    # builder their check-in, so this stays blank and the text still counts.
    proof_image_key = models.CharField(max_length=200, blank=True)
    proof_status = models.CharField(
        max_length=12, choices=ProofStatus.choices, default=ProofStatus.NONE
    )
    coach_reaction = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["-date"]
        constraints = [
            # Many finished cycles a day are fine; two OPEN ones are not —
            # that would mean two tasks on the hook at once, and it makes a
            # double-tapped "Declare it" idempotent.
            models.UniqueConstraint(
                fields=["goal", "date"],
                condition=models.Q(deleted_at__isnull=True, pm_proof_text=""),
                name="one_open_checkin_per_goal_per_day",
            )
        ]

    def __str__(self):
        return f"{self.goal_id} @ {self.date}"


class GoalRetirement(SoftDeleteModel):
    """A goal's last words, written when it stops being active.

    The numbers are a SNAPSHOT taken at retirement, not a live query. Re-deriving
    them later would read today's state onto a historical row — the same mistake
    CheckIn.phase and Goal.__str__ already carry comments about.

    Nothing here is a self-assigned verdict. The builder writes prose; whether
    the idea was actually tested is computed from proofs they had to earn
    (gates.reads_as), because a flaker asked to classify their own exit will
    always pick the flattering label.
    """

    class Outcome(models.TextChoices):
        ABANDONED = "ABANDONED", "Abandoned"
        COMPLETED = "COMPLETED", "Completed"

    goal = models.OneToOneField(
        Goal, on_delete=models.CASCADE, related_name="retirement"
    )
    outcome = models.CharField(max_length=12, choices=Outcome.choices)
    reason = models.TextField()
    phase_reached = models.CharField(max_length=12, choices=Phase.choices)
    # Every accepted proof, whatever phase stamped it — what the builder
    # actually banked, and what the archive shows them.
    accepted_proofs = models.PositiveIntegerField(default=0)
    # The VALIDATION-onward subset. Narrower on purpose, and used for exactly
    # one thing: whether "the idea was disproved" holds up. That claim means
    # real people said no, so IDEA write-ups can't buy it.
    contact_proofs = models.PositiveIntegerField(default=0)
    days_active = models.PositiveIntegerField(default=0)
    best_streak = models.PositiveIntegerField(default=0)
    coach_reaction = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.goal_id}: {self.outcome}"


class Message(SoftDeleteModel):
    class Role(models.TextChoices):
        USER = "USER", "User"
        COACH = "COACH", "Coach"
        # Not a turn: the app telling the builder something about the
        # conversation itself, which today is only "that one didn't go
        # through". It has to be a row rather than a client-side flourish
        # because the refetch that ends every turn would otherwise wipe the
        # bubble the builder is looking at — but stored as COACH it became a
        # thing Masterji said, indistinguishable from coaching a week later
        # and fed back to the model as its own words on the next turn.
        SYSTEM = "SYSTEM", "System"

    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=8, choices=Role.choices)
    content = models.TextField()
    # The phase the conversation was in, stamped once. Reading it off the goal
    # instead would report today's phase for a message sent weeks ago.
    phase = models.CharField(max_length=12, choices=Phase.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"


class ProofAttempt(SoftDeleteModel):
    """A proof submission Masterji pushed back, preserved when the builder
    answers it with a new one.

    The check-in's own proof fields always hold the CURRENT submission; this
    table is the trail of the tries before it. Written archive-before-
    overwrite in the prove view, so the happy path (first proof accepted)
    never creates a row. Every row here is by construction a pushed-back try
    — an accepted proof closes the cycle and can never be overwritten.

    This table is also what keeps evidence honestly attributed: before it
    existed, a resubmission overwrote the text but left the old image key on
    the check-in, so an accepted proof could end up wearing the screenshot
    of the rejected try.
    """

    checkin = models.ForeignKey(
        CheckIn, on_delete=models.CASCADE, related_name="attempts"
    )
    text = models.TextField()
    url = models.URLField(blank=True)
    image_key = models.CharField(max_length=200, blank=True)
    reaction = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["created_at"]

    def __str__(self):
        return f"pushed-back try on {self.checkin_id}"


class PhaseTransition(SoftDeleteModel):
    goal = models.ForeignKey(
        Goal, on_delete=models.CASCADE, related_name="transitions"
    )
    from_phase = models.CharField(max_length=12, choices=Phase.choices)
    to_phase = models.CharField(max_length=12, choices=Phase.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.goal_id}: {self.from_phase} → {self.to_phase}"


class ChangelogEntry(SoftDeleteModel):
    """What has changed in the product, in the builder's language.

    The only table here that belongs to nobody: it's the same list for every
    reader, edited from the admin and served to signed-out visitors too.
    Content is deliberately editorial — an entry is written when a change is
    something a builder would notice, which is not the same set as commits.

    Two switches, on purpose: `is_active` is publication (write an entry now,
    show it when the change is live, retire it later without losing the text),
    while `deleted_at` is the house-wide soft delete. Only rows that are both
    active and undeleted are served.
    """

    class Kind(models.TextChoices):
        NEW = "NEW", "New"
        CHANGED = "CHANGED", "Changed"
        FIXED = "FIXED", "Fixed"
        METHOD = "METHOD", "Method"

    # The day the change reached builders, not when the row was typed — those
    # differ, and the date on a changelog is a claim about the product.
    shipped_on = models.DateField()
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.CHANGED)
    title = models.CharField(max_length=120)
    body = models.TextField()
    is_active = models.BooleanField(
        default=True, help_text="Unticked entries are kept but not shown to anyone."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(SoftDeleteModel.Meta):
        # Newest first, and within a day the later-created row leads: several
        # changes a day is the normal case, and `shipped_on` alone can't
        # order them.
        ordering = ["-shipped_on", "-id"]
        verbose_name_plural = "changelog entries"

    def __str__(self):
        return f"{self.shipped_on} {self.title}"
