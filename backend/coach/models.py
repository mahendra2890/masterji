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
