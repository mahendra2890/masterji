"""Masterji's state machine lives in these rows, not in the LLM.

A user has at most ONE active goal (database constraint — the product
thesis is one thing at a time). The goal walks IDEA → VALIDATION → BUILD →
LAUNCH, and every transition is earned with accepted proofs (see gates.py).
Check-ins are the daily declare-AM / prove-PM loop; messages are the chat
transcript. Tenancy rule: views filter by request.user, so foreign ids 404.
"""

import re
import secrets

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
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


# Where the one number lives. TRACTION and only TRACTION, keyed off the PHASE
# rather than off the transition into it, and that is the whole answer to the
# awkward part of putting this at the end of the ladder: TRACTION is terminal, so
# "entering the phase" is the last transition there is and a builder who arrived
# before this shipped will never make another one. An invitation that fired on
# the advance would be invisible to exactly the builders who got furthest. So the
# question the server asks is "are they in TRACTION, and have they named it yet",
# which a dashboard load can answer on any morning — including the first one
# after a deploy.
#
# HERE rather than in views, where it was first written, because it is no longer
# only a view's business: prompts.suggest_proof_tool asks the same question when
# it decides whether the schema has a metric_value argument in it, and two copies
# of "the metric lives at TRACTION" would be two things to move on the day a
# second phase gets a number.
METRIC_PHASE = Phase.TRACTION


class Goal(SoftDeleteModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        ABANDONED = "ABANDONED", "Abandoned"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals"
    )
    title = models.CharField(max_length=200)
    # The idea itself, as opposed to its headline. `title` is 200 characters and
    # was the whole of what this row knew about the thing being built — so the
    # coach's prompt sent a name, #63's pivot had nothing to hand the successor,
    # and the only thing a builder could sharpen after committing was the
    # wording (#114).
    #
    # {"text": str, "parts": [bar key, ...], "source": "PROOF"|"BUILDER",
    #  "written_at": iso} — empty dict until something fills it.
    #
    # `text` is prose and not the four parts as fields, and that is a finding
    # rather than a shortcut: bar.labels() returns which parts a proof
    # satisfied, never their values ("the keys only, never the values, because
    # the values are the proof text" — CheckIn.proof_parts). The values exist
    # structured for exactly one turn, inside the suggest_proof arguments, and
    # are composed to prose before anything is saved. So the honest body of the
    # idea available today is the accepted IDEA proof's own words, and `parts`
    # records which of the four it covered. The dict shape is what lets #163
    # add per-part keys later without a second migration.
    brief = models.JSONField(default=dict, blank=True)
    # The one-liners parked in the workshop this goal came out of, copied at
    # commit. Empty for a goal typed without a room.
    #
    # The tiebreak produces one winner and two survivors, and the survivors
    # used to die at the moment they became useful: a builder whose idea looks
    # dead on day 4 had to retire the goal to reach a room at all, and the
    # other two candidates were gone when they got there.
    #
    # Every candidate the room parked, including the one this goal came from,
    # and that is deliberate. The commit box is free text — a builder may
    # commit a candidate, the coach's suggested title, or something they typed
    # over both — so no server can know which one-liner became this goal, and
    # a wrong exclusion would lose exactly the thinking this field exists to
    # keep. Still bare strings, still at most Workshop.MAX_CANDIDATES.
    considered = models.JSONField(default=list, blank=True)
    phase = models.CharField(max_length=12, choices=Phase.choices, default=Phase.IDEA)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    # Proofs only count toward the gate if earned in the current phase.
    phase_entered_at = models.DateTimeField(auto_now_add=True)
    # The Monday of the most recent week this goal's digest has been CONSIDERED
    # for (coach/weekly.py), which is not the same as written: a week with no
    # check-ins in it produces no message and still moves this, so the question
    # is asked once a week rather than on every dashboard load.
    #
    # A stored marker rather than something derived from the messages, because
    # the trigger is lazy — there is no scheduler on this deployment, so "the
    # first request of a new week" is whichever request happens to arrive
    # first, and the dashboard refetches after every turn. Matching on the
    # digest's own text would make builder-facing copy load-bearing in two
    # languages and would still race. This claims in one atomic UPDATE.
    last_digest_week = models.DateField(null=True, blank=True)
    # The goal this one came out of, when a builder closed the idea and kept the
    # problem. Null for a goal started from nothing, which is most of them.
    #
    # The commonest real journey event between VALIDATION and BUILD is the idea
    # dying while the problem survives, and the product's memory of those
    # hard-won interviews used to die with the goal — ARCHIVE_BLOCK carries
    # counts and one line, not contents. So the honest move, killing the idea,
    # cost more than limping on, which inverts the whole incentive design.
    #
    # A link and nothing else. It seeds NO count: the successor starts at IDEA
    # with zero proofs, gates.py reads this field never, and IDEA's one proof is
    # still owed — writing the new problem statement is one evening and it is
    # the pivot decision made concrete. What it buys is a prompt block, so the
    # coach does not send a builder back to re-interview Tuesday's person for
    # facts already on the family record.
    #
    # SET_NULL rather than CASCADE: a deleted parent must orphan the successor,
    # never delete a live goal with weeks of its own work on it.
    pivoted_from = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="successors",
    )
    # The ONE number the builder is watching, in their own words — "paid
    # deposits", "orders through the form". Blank until they name one, which is
    # most of the ladder: this is asked for at TRACTION and nowhere else.
    #
    # launch-checklist.md has commanded "One metric. Pick the single number that
    # means 'someone got the value' (payments, completed actions — not visits)
    # and watch only that" since the corpus existed, and it was a sentence the
    # server had never seen. TRACTION is where the number belongs rather than
    # LAUNCH: it is the phase with no PROOFS_REQUIRED entry (gates.at_finish_line
    # explains why that absence has to stay), so it is the phase whose last mile
    # has no arithmetic in it — and bar.BAR[TRACTION] already asks for exactly
    # this shape of thing once (`returned`, `paid`: "how much in ₹", "what they
    # did the second time"). A series here is that bar kept over time, not a new
    # thing to have declared.
    #
    # NEVER A GATE. gates.py does not read this field, PROOFS_REQUIRED gains no
    # TRACTION entry, and a flat number refuses nothing — same terms as the
    # launch date. It is voice and record: the coach is handed the last two
    # values as facts, and the record renders the series.
    #
    # Set once and editable, and the recorded slip that makes editing honest is
    # NOT stored here — see CheckIn.metric_label. A rename with nothing counted
    # under the old name is a builder fixing their own wording; a rename after
    # three days of numbers is the vanity swap the playbook's "watch only that"
    # is aimed at, and the series is where the difference shows.
    metric_name = models.CharField(max_length=60, blank=True)
    # This morning's task as Masterji has heard it, written from work the
    # builder described in conversation (the suggest_declaration tool). The
    # morning's mirror of CheckIn.proof_offer, and an OFFER on exactly the same
    # terms: it fills the declare box and nothing else. Declaring stays a press.
    #
    # ON THE GOAL, not on a CheckIn, because at the moment it is written there
    # is no CheckIn to hang it on — DeclareView is what creates that row, which
    # is the whole situation this tool exists for. Letting the chat open an
    # undeclared row instead would change what a CheckIn means: streaks.py
    # counts a declaration and a proof, and loop_report counts rows as
    # check-ins, so a row that exists because a model guessed would corrupt
    # both. A field here adds nothing to the row semantics and nothing to the
    # gates — gates.py does not read it.
    declaration_offer = models.TextField(blank=True)
    # The builder's own date on the day that draft was written. An offer is
    # about ONE morning: read back on Wednesday, Tuesday's draft is a task
    # nobody is doing, sitting in the box a fresh day is declared from. Kept as
    # a date rather than swept by a job because the only clock that can answer
    # "is this still today" is the client's, and it arrives on the request that
    # reads the offer (views._client_day). NULL whenever the offer is empty.
    declaration_offer_date = models.DateField(null=True, blank=True)
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
        indexes = [
            # `views._active_goal` — filter(user, status=ACTIVE).first(), which
            # runs before almost every authenticated request in the product.
            #
            # Partial on the soft-delete predicate rather than carrying
            # `deleted_at` as a column: `SoftDeleteManager` adds
            # `deleted_at IS NULL` to every query through the default manager,
            # so the condition is free here and the index stays the size of the
            # live table. See the note on CheckIn for why that beats indexing
            # the column itself.
            models.Index(
                fields=["user", "status"],
                condition=models.Q(deleted_at__isnull=True),
                name="coach_goal_active_idx",
            ),
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
    # The hour the builder said tonight's proof would land, 0-23 on their own
    # clock, or NULL because naming one is optional and most declarations
    # won't. Set by the declare flow and by nothing else.
    #
    # VOICE, NEVER GATE. streaks.py does not read it and gates.py does not read
    # it: a proof filed at 23:40 against a named 21:00 counts exactly as much
    # as one filed at 20:59, and the day is complete either way. What it buys
    # is that views._today_state can put the builder's own word in front of the
    # coach — "they said it would land by 21:00" — so he can hold them to
    # something they chose rather than to a rule the product imposed. That
    # works with no clock anywhere in the system, which is the only reason
    # this field is here.
    #
    # It is deliberately NOT a promise about when anything fires. #142 settled
    # that the only scheduler this project will have is a free-tier GitHub
    # Actions `schedule:`, whose runs are delayed by minutes to hours; the
    # hourly tick that reads this field to pick who is overdue rides in with
    # #87's job, and even then delivers "shortly after the hour you named"
    # rather than at it. Every string written around this field has to survive
    # that, because a commitment device that arrives late teaches the builder
    # the hour was decorative.
    due_hour = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
    )
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
    # The same task, rewritten to clear the bar the reaction just named — one
    # sentence, in the builder's own terms. Written by the same judging call as
    # declaration_reaction and blank on the days that call has no complaint:
    # "an empty reaction is the compliment" extends to it unchanged, and a
    # sharpening offered against a task that was already specific enough is
    # noise with a button under it.
    #
    # An OFFER, never a record — CheckIn.proof_offer's rule, one screen earlier.
    # It fills the declare box and the builder presses Declare it, which
    # re-runs the judgement over whatever they actually send. So the model does
    # not get to hand itself the wording it will later grade: a suggestion
    # accepted verbatim is read back as a declaration rather than trusted as
    # one, and it carries no proof_ask with it.
    sharpened = models.TextField(blank=True)
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
    # the evening's judgement (judging._react_to_proof). Notes are a record of
    # what the builder said, never a verdict — a partial draft that gets filed
    # is judged like any other proof.
    proof_missing = models.TextField(blank=True)
    # Today's reading of the one number as Masterji heard it said — the number
    # half of the same draft, written by the same suggest_proof call and
    # provisional exactly as far as the rest of it is. It PREFILLS the box on
    # the evening form and does nothing else.
    #
    # An OFFER, never a record, and the distance between this field and
    # metric_value below is the whole of that rule: no reading exists until the
    # builder files, views._record_metric stays the only writer of metric_value,
    # and every reader of the series — the card's sparkline, the prompt's recent
    # readings, the export — reads metric_value. Nothing reads this but the form.
    #
    # NULL, not 0, when there is nothing drafted. Zero is a reading somebody
    # took: "nobody came back today" is a fact about the day and one of the more
    # useful points in the series, so it cannot double as "he heard no number".
    metric_offer = models.IntegerField(null=True, blank=True)
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
    # Whether that link answered when the server checked it (coach.links).
    # NULL is a third state and the important one: it means no answer was
    # obtained — timeout, a target we declined to fetch, no link at all — and it
    # must never read as "dead", because a builder whose campus wifi ate the
    # request has done nothing wrong. Same contract as proof_image_key:
    # corroboration, never the proof itself, and nothing the gate reads.
    url_alive = models.BooleanField(null=True, default=None)
    # When that answer came back. Only set when there is an answer to timestamp,
    # so a row with url_alive NULL never claims a check happened.
    url_checked_at = models.DateTimeField(null=True, blank=True)
    # Opaque object-storage key for a screenshot backing tonight's proof.
    # Corroboration, never the proof itself: a failed upload must not cost the
    # builder their check-in, so this stays blank and the text still counts.
    proof_image_key = models.CharField(max_length=200, blank=True)
    proof_status = models.CharField(
        max_length=12, choices=ProofStatus.choices, default=ProofStatus.NONE
    )
    coach_reaction = models.TextField(blank=True)
    # Today's reading of the one number the builder chose to watch
    # (Goal.metric_name), and the name it was read under. TRACTION only, and
    # NULL on almost every row in the table — most days of most goals were never
    # asked for a number.
    #
    # NULL is the only "no value" there is, which is why this is nullable rather
    # than defaulted: zero is a real and important reading — the day the metric
    # did not move is the day the coach most needs to see — and a default of 0
    # would make every untouched row in the product claim it.
    #
    # Nothing reads this that can refuse anything. gates.py has never heard of
    # it, the judge is not shown it, and a day with a number and no proof banks
    # nothing while a day with a proof and no number banks everything it always
    # did.
    metric_value = models.IntegerField(null=True, blank=True)
    # The metric's name AS IT STOOD when this value was recorded, stamped beside
    # it and never rewritten — the same discipline as `phase` above, and for a
    # closely related reason.
    #
    # This is the recorded slip. Goal.metric_name is one field, so a rename would
    # otherwise re-label every value already on the record: three evenings that
    # counted deposits would silently become three evenings of signups, and the
    # coach would be handed "signups: 3 → 5" as a fact about days nobody ever
    # counted signups on. The record being trustworthy because the server wrote
    # it is the whole product, and that is the one direction nothing would
    # detect.
    #
    # With the name on the row the trail needs no second table and no timestamp
    # comparison — which matters, because a name row would carry server UTC and
    # these values carry the CLIENT's date, and `phase` above documents what
    # happens when those two are asked to agree. A swap shows up as what it is:
    # the series says "deposits 3, 4, 5" and then "signups 40", and a rename
    # nothing was ever counted under leaves no mark, because nothing slipped.
    metric_label = models.CharField(max_length=60, blank=True)
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
        indexes = [
            # `gates._banked` — the hottest query in the product. It runs on
            # every state load, every chat turn (prompt assembly) and every
            # advance, and it is the query the gate's own refusal is computed
            # from, so nothing a builder does gets far without it.
            models.Index(
                fields=["goal", "phase", "proof_status"],
                condition=models.Q(deleted_at__isnull=True),
                name="coach_checkin_gate_idx",
            ),
            # `_open_checkin`, `_latest_checkin`, `_carried_over`, `_offer_target`
            # — all of them filter(goal, date) and then take the newest by
            # `-created_at`, so the sort column belongs in the index or the
            # ordering is a sort over the match set.
            models.Index(
                fields=["goal", "date", "-created_at"],
                condition=models.Q(deleted_at__isnull=True),
                name="coach_checkin_day_idx",
            ),
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
    # The one thing on this row that can be read without an account, and only
    # if the builder switched it on. Unguessable rather than sequential: the
    # slug IS the access control, so a numeric id would make every closed goal
    # in the database walkable by anybody who found one link.
    #
    # Null means private, which is the default and the state every existing row
    # is in. Revoking is setting it back to null, and it is a different slug if
    # they ever turn it on again — a link handed out once and regretted has to
    # be able to stop working.
    #
    # Nothing about what the page SHOWS lives here: that is the public view's
    # business, and it renders computed facts only. The builder's own prose —
    # the reason they closed it, every proof they ever wrote — never leaves
    # this server through that endpoint.
    share_slug = models.CharField(
        max_length=22, null=True, blank=True, unique=True, default=None
    )
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

    class Kind(models.TextChoices):
        """What a SYSTEM row is, for the rows where role alone is not enough.

        SYSTEM meant exactly one thing — "that turn didn't land" — until the
        weekly digest became the second thing the app says in its own voice,
        and the two want opposite treatment: a notice carries a "Send it
        again" button built from the turn directly above it, and hanging that
        off a Monday-morning summary would offer to resend a sentence from
        last week. Read only on SYSTEM rows; USER and COACH carry the default
        and nothing looks at it.
        """

        NOTICE = "NOTICE", "Notice"
        DIGEST = "DIGEST", "Digest"

    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=8, choices=Role.choices)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.NOTICE)
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
    # The answer THIS try's link got, for the same reason image_key is here: a
    # retry with a working link must not leave the refused try wearing it.
    url_alive = models.BooleanField(null=True, default=None)
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
    # One line, in the builder's words: what THIS phase is going to produce.
    #
    # A phase has a bar and no shape. guidance.PHASE_HINT[BUILD] says "smallest
    # thing a real user can touch this week" — for every builder, forever — so
    # the coach can tell whether tonight's task is on-phase for BUILD in
    # general, and never whether it is the thing this builder said on Monday.
    # This is the missing half, and it costs no rung on the ladder.
    #
    # Here rather than on Goal because it is a fact about ONE phase: a goal that
    # reaches TRACTION passed through four of these, and a field on the goal
    # would keep only the last one — the record would then say the builder had
    # always meant to do whatever they most recently said.
    #
    # Never a gate. gates.try_advance does not read it, blank is a legal and
    # common value, and skipping it advances the phase exactly as before.
    intent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.goal_id}: {self.from_phase} → {self.to_phase}"


class LaunchCommitment(SoftDeleteModel):
    """A date the builder named for launching, and every time they moved it.

    APPEND-ONLY, and that is the whole mechanism. A row is never edited: moving
    the date writes a second row, so what the record holds is not "26 August"
    but "declared 24 August, moved once, currently 26 August". The visible slip
    trail IS the consequence — the commitment-device insight without a stake,
    because nothing here refuses anything. `gates.PROOFS_REQUIRED` is untouched,
    a blown date refuses no proof and costs no streak, and the coach can say
    "nine days out" only because a builder chose to say it first.

    Why this exists: shipping-cadence.md's diagnosis is that BUILD dies from
    drift in week three — "almost done" true for ten days running — and the
    playbook already instructs "set the launch date before the build feels
    ready". That was advice the server could not see, cite or count.

    The pond comes with it because launch-checklist.md's ladder is where a
    launch actually happens, and "launching" with no room in mind is the drift
    one step later. Named rungs rather than free text: the ladder is the
    playbook's, and a builder inventing a fifth rung is a builder avoiding the
    four.
    """

    class Pond(models.TextChoices):
        # launch-checklist.md's ladder, in its order. The labels are the
        # playbook's own words — two copies of a rung would drift, and this one
        # is the copy a builder reads on a dashboard.
        TALKED = "TALKED", "The ones who talked to you"
        ROOMS = "ROOMS", "The rooms they sit in"
        PUBLIC = "PUBLIC", "The public ponds"
        ASK = "ASK", "The ask — charging or committed sign-ups"

    goal = models.ForeignKey(
        Goal, on_delete=models.CASCADE, related_name="launch_commitments"
    )
    date = models.DateField()
    pond = models.CharField(max_length=8, choices=Pond.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.goal_id}: launch {self.date} ({self.pond})"


class Workshop(SoftDeleteModel):
    """The room before the goal — a metered vestibule, not a phase.

    Every other row in this file is downstream of a Goal, which is exactly the
    hole this fills: ChatView, DeclareView and ProveView all refuse with "Set a
    goal first", so a builder's first contact with Masterji is the welcome
    message written *after* the commit that frightened them. A workshop is where
    the coach can speak before there is anything to declare.

    What keeps it a vestibule rather than the hiding place this product exists
    to refuse, all of it enforced in server code and none of it in a prompt:

    - ONE open workshop per user, the conditional-unique pattern Goal already
      uses for one_active_goal_per_user. The pre-goal room is available only
      while no goal is active — the exact inverse of the guard above — and the
      REOPENED room is its mirror: available only while one IS, once per goal,
      with a smaller meter. The room answered "I don't have an idea yet"; it
      did not answer "I have one and I no longer believe in it", which is the
      same sentence four days later, and the only way to get a room back for it
      was to bury the goal first.
    - A hard turn cap (views.WORKSHOP_TURNS) counted off WorkshopMessage rows.
      Turns spent means the only door left is Commit.
    - At most three parked candidates. An unbounded backlog of ideas is a
      content library growing, which is consumption dressed as progress; three
      makes collecting impossible and choosing the only remaining move.

    It banks nothing and advances nothing. gates.py never reads this table —
    there is no CheckIn, no proof and no phase here to read — and committing a
    goal spends the workshop, so the next one opens only after that goal closes.
    """

    #: The most candidates that may be parked before the room flips to a
    #: forced choice. Lives here beside the field it bounds; the refusal is in
    #: the view, where the count is a len() with no model in the loop.
    MAX_CANDIDATES = 3

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        # The room a builder comes back to once the goal exists and has stopped
        # convincing them. A different room, not the same one unlocked: fewer
        # turns, no candidates, no suggested title, and one per goal ever.
        REOPENED = "REOPENED", "Reopened"
        SPENT = "SPENT", "Spent"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workshops"
    )
    # Null for the room before the goal, which is every OPEN and SPENT row: that
    # room exists precisely because there is nothing to hang it off. Set on a
    # REOPENED row, which is what makes "once per goal" a database fact rather
    # than a count somebody has to remember to take.
    goal = models.ForeignKey(
        "Goal",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="workshops",
    )
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.OPEN
    )
    # One-liners the builder parked, oldest first. Deliberately bare strings
    # with no research, no links and no scores attached: a candidate that can
    # carry a reading list is a candidate you can hide behind, and these die
    # with the workshop rather than becoming a backlog to maintain.
    candidates = models.JSONField(default=list, blank=True)
    # The title the coach's tiebreak landed on, kept only so it survives a
    # closed tab. It fills the commit box and never commits — the GOAL_EXAMPLES
    # bargain: one tap from a suggestion to a database constraint is how a
    # builder ends up coached on somebody else's idea. Same width as Goal.title
    # because that is the box it is going into.
    suggested_title = models.CharField(max_length=200, blank=True)
    # What the room established about the idea, in the shape Goal.brief uses —
    # written when the coach calls suggest_goal, copied onto the goal at commit
    # and never read again after that.
    #
    # It lives here rather than being extracted at commit because #211 settled
    # that the bar's part VALUES are never stored: they exist structured for
    # exactly one turn, inside a tool call's arguments. suggest_goal is the
    # model call that already knows this idea — it is the one fired when the
    # tiebreak lands — so the four parts ride it and the commit stays a
    # database write with no model in it.
    #
    # `parts` is which of bar.BAR[IDEA]'s four the room actually covered,
    # computed by bar.labels over the same arguments. It is provenance, not a
    # verdict: nothing here is judged, nothing banks, and IDEA's one proof is
    # owed in full the same evening either way.
    brief = models.JSONField(default=dict, blank=True)
    # The same four parts, counted as the conversation goes rather than once at
    # the tiebreak — the forecast the room shows the builder ("2 of the 4 pieces
    # IDEA asks for"), which `brief` cannot be because suggest_goal fires once,
    # at the end, when the room is nearly over.
    #
    # Keys only, never the values, for the same reason CheckIn.proof_parts holds
    # keys: the values are what the builder said and what they said is already
    # on the transcript rows. A forecast, not a bank — gates.py does not read
    # it, PROOFS_REQUIRED does not know it exists, and committing spends the
    # workshop this hangs off, so the count dies with the room.
    sketch_parts = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(SoftDeleteModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="OPEN", deleted_at__isnull=True),
                name="one_open_workshop_per_user",
            ),
            # And one reopened room per GOAL, ever — not one at a time. The
            # meter is what makes the room a room rather than a hiding place,
            # and a meter you can reset by walking out and back in is not one.
            # Keyed on the goal rather than on (goal, status) for exactly that
            # reason: a spent reopening must still occupy the slot.
            #
            # Nullable FKs do not collide in a unique index, so every pre-goal
            # room — all of them goal-less — is untouched by this.
            models.UniqueConstraint(
                fields=["goal"],
                condition=models.Q(deleted_at__isnull=True),
                name="one_workshop_per_goal",
            ),
        ]

    def __str__(self):
        return f"Workshop {self.pk} ({self.status})"


class WorkshopMessage(SoftDeleteModel):
    """A turn in the workshop. Separate from Message because Message hangs off a
    Goal, and the whole point of this room is that there isn't one yet.

    No phase stamp for the same reason: there is no phase here. USER rows are
    what the turn cap counts, which is why the cap is a property of the
    transcript rather than a counter anybody has to remember to increment.
    """

    class Role(models.TextChoices):
        USER = "USER", "User"
        COACH = "COACH", "Coach"
        SYSTEM = "SYSTEM", "System"

    workshop = models.ForeignKey(
        Workshop, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=8, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"


#: The alphabet a join code is minted from: uppercase letters and digits,
#: minus the five that get misread off a projector or a phone screen — O and 0,
#: I and 1 and L. A code is read aloud in a room and typed by forty people, so
#: the character set is a usability decision before it is a security one.
JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 8


def mint_join_code() -> str:
    """A fresh code. 31^8 ≈ 8.5e11, which is not the security — the membership
    check is (see Cohort) — but is enough that guessing is not a strategy.

    A module-level function rather than a classmethod because it is a field
    default, and Django serialises a default into every migration that touches
    the column: it has to be importable by name forever.
    """
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


class Cohort(SoftDeleteModel):
    """An E-Cell's forty builders, as a LENS over rows that already exist.

    Nothing here computes anything, counts anything, or can be earned. A cohort
    holds a name and a code; the numbers on its board are the same
    `accepted_proofs_total`, `contact_proofs` and streak the product already
    counts for the builder themselves, read through a membership. `gates.py`
    does not know this table exists and never will.

    That is the whole competitive argument. NEC and NSRCEL cohorts rank on
    jury-judged self-reports and pitch milestones, so the loudest deck wins;
    this board has no field a builder can write on it. What a coordinator sees
    is what the gate accepted, and there is no version of this table that lets
    them change it.

    **There is no coordinator in this model.** No role, no owner FK, no create
    endpoint — a cohort is made by staff in the admin, and the coordinator is a
    person holding the code and an ordinary membership row, reading the same
    board as everybody else. It is the strongest available form of "no
    coordinator can bank or unbank anything": not a permission that is checked,
    but a capability that was never modelled.

    No owner FK is also what keeps `accounts.erasure` safe. That walks the
    model graph soft-deleting everything hanging off a user, so a `created_by`
    here would mean one coordinator deleting their account took the board down
    for the other thirty-nine.
    """

    name = models.CharField(max_length=120)
    # What a builder types to join, and the whole of how joining happens.
    #
    # No expiry field, deliberately: a deadline nobody set is a support ticket
    # in three months. Rotation IS the revocation — writing a new code here
    # leaves the old string matching nothing, so there is no revoked state to
    # reason about, and closing a cohort to new joins is rotating to a code
    # nobody has.
    #
    # Rotating NEVER touches members (see CohortMember). A code is an
    # invitation, not a session; a rotation that ejected forty people would
    # make the safe operation the dangerous one.
    #
    # Unique across soft-deleted rows too — `unique=True` is a database
    # constraint and does not read `deleted_at` — which is the wanted
    # behaviour: a retired cohort's code must not come back up in somebody
    # else's hands.
    join_code = models.CharField(max_length=32, unique=True, default=mint_join_code)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["name"]

    @staticmethod
    def normalise(code: str) -> str:
        """One code, however it was typed.

        `abcd-2345`, `ABCD 2345` and `abcd2345` are the same code: it is read
        off a slide and typed on a phone, and a join that failed on a space
        would be indistinguishable from a wrong code. Bounded at the column's
        width so a megabyte in the `code` field is a miss rather than a query.
        """
        return re.sub(r"[\s-]", "", code or "").upper()[:32]

    def __str__(self):
        return self.name


class CohortMember(SoftDeleteModel):
    """One builder's agreement to be counted where their peers can see it.

    **Joining by code IS the consent, and this row is the whole of it.** A
    builder who has not joined is invisible to every cohort surface — not
    listed, not ranked, not counted in an aggregate, not discoverable by code —
    because every query in `coach/cohorts.py` starts from this table filtered
    to the requester. It is enforced in the queryset and not in a serializer,
    for the reason tenancy is enforced in the queryset everywhere else here: a
    check that lives at the edge of the response is a check somebody adds a
    second caller around.

    Leaving soft-deletes this row and touches nothing else. `Goal`, `CheckIn`,
    `PhaseTransition` and `GoalRetirement` do not know a cohort existed, so a
    builder's own record is identical the day after they leave. That is the
    inverse of the usual arrangement and it is the point: what they agreed to
    is being *shown*, and withdrawing it costs them nothing they earned.

    Deleting the account leaves every cohort with no code of its own —
    `accounts.erasure._descend` walks the model graph soft-deleting every
    `SoftDeleteModel` that hangs off the user, and this is one. Pinned by a
    test, because the thing that makes it true is a graph walk somebody could
    one day replace with a hand-written list.
    """

    cohort = models.ForeignKey(
        Cohort, on_delete=models.CASCADE, related_name="members"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cohort_memberships",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["joined_at"]
        constraints = [
            # Joining twice is the same membership, not a second row — a
            # builder who taps the button twice, or pastes the code again next
            # week, must not appear on the board twice.
            #
            # Conditional on the soft-delete predicate like every other
            # constraint in this file, which also makes leaving and rejoining
            # work: the tombstone does not occupy the slot.
            models.UniqueConstraint(
                fields=["cohort", "user"],
                condition=models.Q(deleted_at__isnull=True),
                name="one_membership_per_cohort_per_user",
            )
        ]
        # No `indexes`. Both columns this table is ever queried by are foreign
        # keys, and Django indexes those already; 0071's lesson is that an
        # index earns its place on a named query or it is dead weight, and a
        # partial re-index of an implicitly-indexed column on a table with one
        # row per builder per cohort is not a query plan anybody would notice.
        # The aggregation's cost is on `coach_checkin`, and the indexes there
        # already fit it — see coach/cohorts.py.

    def __str__(self):
        return f"{self.user_id} in {self.cohort_id}"


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
        indexes = [
            # `ChangelogView` — filter(is_active=True), ordered by the Meta
            # above and usually sliced to `?limit=N`. The only unauthenticated
            # endpoint in the product, mounted by every screen including the
            # signed-out landing page and the tour, on a table whose row count
            # only goes one way: the house rule is a row per shipped change.
            #
            # `is_active` is a *condition*, not the leading column, and that
            # distinction is the whole index. Practically every row is active
            # — an entry is written when a change ships and retiring one is
            # rare — so leading with it sorts nothing and skips nothing, and
            # the planner correctly ignores such an index in favour of a scan.
            # Pushed into the partial condition instead, the index holds only
            # the rows this endpoint can return, in exactly the order it
            # returns them: `?limit=N` becomes reading N entries, with no sort.
            models.Index(
                fields=["-shipped_on", "-id"],
                condition=models.Q(deleted_at__isnull=True, is_active=True),
                name="coach_changelog_live_idx",
            ),
        ]

    def __str__(self):
        return f"{self.shipped_on} {self.title}"


class ModelCall(SoftDeleteModel):
    """One call to the model: what it spent, and whose turn caused it.

    Every other row in this file is the builder's record. This one is the
    operator's, and it is the only place in the product where money appears.

    Before this existed the seam wrote its token counts as OpenTelemetry span
    attributes and nothing else, so with `OTEL_EXPORTER_OTLP_ENDPOINT` unset —
    the default, and what production runs — they were discarded at the process
    boundary. Nothing computed cost anywhere. "What has this cost, and who
    spent it" had no answer that did not involve attaching an exporter by hand.

    A row per call rather than a per-user running total, because the questions
    worth asking are about shape rather than sum: which call kind carries the
    spend, whether one builder is an outlier, what a chat turn costs against
    the judgement under it. A counter cannot be asked any of those after the
    fact. The cost is that this table only grows — see the note on the index.
    """

    class Kind(models.TextChoices):
        # What the seam did, not what the product meant by it. `complete` is
        # reached by a retirement summary and by the evening's verdict alike,
        # and guessing intent from the model name would be a lie the day
        # LLM_JUDGE_MODEL is set to LLM_MODEL — which is its default.
        CHAT = "CHAT", "Chat turn (streamed)"
        COMPLETION = "COMPLETION", "Completion"
        VISION = "VISION", "Completion with an image"

    class Source(models.TextChoices):
        """Which table the causing row is in. `Kind` says what the seam did;
        this says what the product was doing when it did it.

        A name and an id rather than a foreign key, and deliberately: the five
        call sites point at four different models, so an FK would need either
        four nullable columns or a generic content-type pair — and the generic
        one cannot be plainly aggregated or joined, which is the only thing
        this table exists to support. The cost, named rather than discovered:
        no referential integrity, so a deleted row leaves a dangling id here.
        That is affordable because nothing reads this pointer on a builder's
        path — it is the operator's own record, read by hand and in aggregate.
        """

        MESSAGE = "MESSAGE", "Chat message"
        WORKSHOP_MESSAGE = "WORKSHOP_MESSAGE", "Workshop message"
        CHECKIN = "CHECKIN", "Check-in"
        GOAL = "GOAL", "Goal"

    # Nullable, and that is a real state rather than a gap. The nudge cron,
    # management commands and the shell all reach the seam with no request and
    # therefore no builder; their spend is the operator's own and still counts.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="model_calls",
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    # The string that was actually sent, not settings.LLM_MODEL read back at
    # display time: the setting is what the NEXT call will use, and a ledger
    # that rewrites its own history the day the model is switched is worthless
    # for the one comparison it exists to support.
    model = models.CharField(max_length=120)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    # Null when nobody can price it — see spend.cost_usd. Decimal rather than
    # float because these get summed, and eight places because a cheap model's
    # single call lands below a micro-dollar and must not round to nothing.
    cost_usd = models.DecimalField(
        max_digits=14, decimal_places=8, null=True, blank=True
    )
    # Which turn caused it. Nullable on both halves, and never backfilled: the
    # nudge cron, management commands and the shell reach the seam with no
    # request behind them and genuinely have no causing row, and every row
    # written before this column existed has no honest value to give it. A null
    # here means "not recorded", which is the truth in both cases.
    source = models.CharField(
        max_length=20, choices=Source.choices, null=True, blank=True
    )
    source_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        # DELIBERATELY NO `ordering`. This is the one table in the project
        # whose whole purpose is aggregation, and a default ordering joins the
        # GROUP BY on `.values()` — which silently splits a per-user total
        # into one row per call and sorts every bulk read on the way. The
        # house has already been bitten by exactly that. Callers that want an
        # order say so; `-created_at` is what the admin asks for.
        indexes = [
            # The two questions this table exists to answer are both
            # per-builder and both recent-first: what has this builder spent,
            # and what did they spend it on. Partial on the live rows for the
            # same reason ChangelogEntry's index is — `objects` filters
            # soft-deleted rows out of every read, so an index carrying them
            # holds rows no query can return.
            models.Index(
                fields=["user", "-created_at"],
                condition=models.Q(deleted_at__isnull=True),
                name="coach_modelcall_user_idx",
            ),
        ]

    def __str__(self):
        return f"{self.model} {self.total_tokens}t {self.kind}"
