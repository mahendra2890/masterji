"""The judgement — what turns a builder's paragraph into a verdict the gate
will count.

Three model calls with one shape — the evening's proof, the morning's
declaration, the closing sentence over a retired goal — and, downstream of the
first, the labels a verdict carried and the two briefs written out of an idea
the gate accepted. Each of the three is LLM garnish over a deterministic
floor, and the floor is the part that is not negotiable: _react_to_proof's is
"unjudged" rather than "accept", and the other two point at it and say the
same.

Separate from llm.py on the argument spend.py already makes against it: that
seam is about reaching a provider, and this is about what the answer is
allowed to decide. Separate from gates.py, which counts what has been banked
and reads none of this. Separate from bar.py and guidance.py, which say what
one night's evidence has to contain — to the server and to the builder
respectively; this module is what happens when a builder claims to have
brought it.

It lived between MetricView and ChatView until there was somewhere else to put
it. views.py keeps the HTTP: read the row, call in here, write the fields,
serialize.

The row-readers at the top are here rather than in views because the judge is
what they exist for — the banked record a verdict is judged against (_banked),
the repeat rule that is arithmetic rather than a reading (_already_banked,
_same_words), and what this builder said the phase was for (_phase_intent).
views still calls them, module-qualified, for the coach's own prompts — which
are built out of the same facts, and must not be able to disagree with the
judge about what a proof was.
"""

import json

from django.conf import settings
from django.utils import timezone
from loguru import logger

from . import bar, guidance, llm, prompts
from .models import (
    CheckIn,
    Goal,
    GoalRetirement,
    ModelCall,
    Phase,
    PhaseTransition,
    ProofAttempt,
)
from .serializers import BRIEF_CHARS

# How much of the banked record travels in a prompt (prompts.RECORD_BLOCK).
#
# Ten is more proofs than any phase asks for — three is the largest bar — so it
# covers the whole of a long VALIDATION and then some, while keeping the block a
# paragraph rather than a transcript. Newest first, so what falls off the end is
# the oldest, which is also the least likely to be re-asked for tonight.
RECORD_LIMIT = 10
# Each proof trimmed to its opening. Enough to recognise which conversation or
# which artifact it was, which is all either reader needs: the coach has to know
# not to ask again, the judge has to know a repeat when it sees one. The
# untrimmed text stays on the record, which is the thing that has to be whole.
RECORD_CHARS = 400


def _current_transition(goal: Goal) -> PhaseTransition | None:
    """The row that opened the phase the goal is in right now, if there is one.

    None in IDEA, always and correctly: nothing unlocked it, so there was no
    moment at which to ask what it would produce. Filtered on to_phase as well
    as taking the newest, because the two can disagree — a goal is moved back
    only by an operator in the admin, and a phase's line has to belong to the
    phase it names rather than to the last advance that happened.
    """
    return (
        goal.transitions.filter(to_phase=goal.phase).order_by("-created_at").first()
    )


def _phase_intent(goal: Goal) -> str:
    """What the builder said the current phase would produce, or ""."""
    transition = _current_transition(goal)
    return transition.intent if transition else ""


def _banked(goal: Goal, exclude: CheckIn | None = None) -> list[dict]:
    """Accepted proofs on this goal, newest first, as facts for a prompt.

    The counterpart of _archive for the goal that is still alive. `_archive`
    carries goals that ended and `notes_block` carries the evening in progress;
    between them sat every day this goal has already banked, which no prompt
    could see. The coach knew "2/3 accepted toward BUILD" and nothing about what
    the 2 were.

    Whatever phase stamped them, deliberately — the same reason
    gates.accepted_proofs_total exists. A conversation the builder had while
    still in IDEA is a conversation they had, and asking them to repeat it
    because the row carries the wrong label is the exact failure this fixes.

    `exclude` is the row being judged right now: it is not ACCEPTED yet, so it
    cannot match, but a resubmission against a PUSHED_BACK row must not be able
    to read itself back either if that ever changes.
    """
    rows = CheckIn.objects.filter(
        goal=goal, proof_status=CheckIn.ProofStatus.ACCEPTED
    ).order_by("-date", "-created_at")
    if exclude is not None and exclude.pk:
        rows = rows.exclude(pk=exclude.pk)
    return [
        {
            "date": row.date.isoformat(),
            "phase": row.phase or goal.phase,
            "declared": row.am_declaration,
            "proof": row.pm_proof_text[:RECORD_CHARS],
        }
        for row in rows[:RECORD_LIMIT]
    ]


def _same_words(text: str) -> str:
    """Proof text flattened for comparison — case and whitespace carry no
    evidence, so two submissions that differ only there are one submission."""
    return " ".join(text.lower().split())


def _already_banked(goal: Goal, checkin: CheckIn, text: str) -> CheckIn | None:
    """An accepted proof on this goal that is tonight's submission again.

    The deterministic half of the repeat problem, and the reason it needs one at
    all: a day may hold several declare→prove cycles (CheckIn's docstring — real
    work counts when it happens) and each accepted proof banks toward the phase,
    so one conversation filed three times in an evening cleared VALIDATION. The
    model could not have known; nothing it was shown reached past tonight's
    refused tries on this one row.

    Exact after flattening, and no looser. The same words twice is arithmetic and
    belongs in server code; a conversation *retold* is a judgement, and it is the
    model's with prompts.RECORD_FOR_JUDGE in front of it. Guessing at
    near-matches here would refuse genuine second work by similarity, which is a
    gate that fails in the one direction this product cannot afford.
    """
    normalised = _same_words(text)
    if not normalised:
        return None
    # The comparison is normalised text, which no database does portably, so the
    # scan happens here — over three columns rather than whole rows, since a
    # goal's whole accepted history is what has to be looked at.
    for other in (
        CheckIn.objects.filter(goal=goal, proof_status=CheckIn.ProofStatus.ACCEPTED)
        .exclude(pk=checkin.pk)
        .order_by("-date", "-created_at")
        .only("pk", "date", "pm_proof_text")
    ):
        if _same_words(other.pm_proof_text) == normalised:
            return other
    return None


def _react_to_retirement(retirement, verdict: str) -> str:
    """LLM garnish over a deterministic floor, same as _react_to_proof: if the
    model is down the goal still retires, with a stock line."""
    try:
        system = prompts.RETIREMENT_SYSTEM.format(
            respect_rule=prompts.RESPECT_RULE,
            outcome=retirement.outcome,
            verdict=verdict,
            phase=retirement.phase_reached,
            accepted_proofs=retirement.accepted_proofs,
            contact_proofs=retirement.contact_proofs,
            days=retirement.days_active,
            best_streak=retirement.best_streak,
        )
        # Not the judge model, and that is a decision rather than an oversight:
        # the verdict here was already computed by gates.reads_as before this
        # call, out of proofs the builder had to earn. All the model contributes
        # is the sentence, so it belongs with the conversation, not the verdicts.
        #
        # Booked to the goal rather than to the retirement: the retirement is a
        # snapshot of the goal, and "what did this goal cost" is the question
        # anyone reading the ledger for a closed goal is actually asking.
        with llm.attributing(ModelCall.Source.GOAL, retirement.goal_id):
            return llm.complete(system, retirement.reason)
    except Exception as e:
        logger.error(f"Retirement reaction failed: {e}")
        stock = (
            prompts.STOCK_SHIPPED
            if retirement.outcome == GoalRetirement.Outcome.COMPLETED
            else prompts.STOCK_RETIRED
        )
        return stock[verdict]


def _react_to_declaration(goal: Goal, text: str) -> tuple[str, str, str, str]:
    """Read this morning's task: does it belong to the phase, what would make it
    sharper, and what would prove it tonight? Returns (fit, reaction, sharpened,
    proof_ask).

    Advisory only, by design. Declaring is never refused — a builder is
    allowed to spend a day off-phase, and the gate at the end of the phase is
    what makes that cost something. Blocking here would hand the model a veto
    it must not have, and turn a coaching moment into an invisible refusal.

    `sharpened` does not soften that and is not the veto arriving by another
    door: it is a sentence with a button under it, on a card where the builder
    can equally reword the task themselves or leave it exactly as they wrote it.
    What it removes is the dead end — a critique naming a problem with no
    control under it, in the one room where acting on it is free.

    Same deterministic floor as _react_to_proof: any failure logs and leaves
    the check-in UNJUDGED with no tailored ask, so the form falls back to the
    phase's static proof hint rather than showing nothing.

    Fenced like the evening's proof, and for a less obvious reason than that one:
    the `proof_ask` this produces is fed to the evening as "this morning you
    asked them to bring: …", so a declaration carrying an instruction gets to
    write tonight's bar — in a room the builder has already left.
    """
    try:
        system = prompts.DECLARATION_SYSTEM.format(
            respect_rule=prompts.RESPECT_RULE,
            evidence_rule=prompts.EVIDENCE_NOT_INSTRUCTIONS,
            phase=goal.phase,
            phase_rules=prompts.PHASE_RULES[Phase(goal.phase)],
            proof_hint=guidance.PROOF_HINT[Phase(goal.phase)],
            # What this builder said this phase was for, if they said anything.
            # It is what the morning's reading has never had: the phase hint is
            # the same sentence for every builder in the same position — and
            # since guidance.BEATS, that position includes how far into the phase
            # they are, which is still not what THIS builder decided the phase
            # was for. So "is this the work this phase is for" could only ever be
            # answered about phases in general without this line.
            intent=prompts.declaration_intent(_phase_intent(goal)),
        )
        # The judge model: this call decides declaration_fit and writes the
        # proof_ask the evening is then graded against, so it is a verdict with
        # a second verdict downstream of it, not a turn of conversation.
        raw = llm.complete(
            system,
            prompts.fence_submission(text),
            model=settings.LLM_JUDGE_MODEL,
        )
        payload = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        fit = (
            CheckIn.DeclarationFit.OFF_PHASE
            if payload.get("fit") == "off_phase"
            else CheckIn.DeclarationFit.ON_PHASE
        )
        reaction = str(payload.get("reaction") or "")
        return (
            fit,
            reaction,
            # Dropped when there is no complaint to fix. The prompt already says
            # so, but the pairing is what makes the card honest — a sharpening
            # under nothing reads as a critique the builder never got, and the
            # button under it as a correction they are being asked to accept for
            # a reason nobody gave. Empty reaction, empty offer, no control.
            str(payload.get("sharpened") or "") if reaction else "",
            str(payload.get("proof_ask") or ""),
        )
    except Exception as e:
        logger.error(f"Declaration reaction failed: {e}")
        return CheckIn.DeclarationFit.UNJUDGED, "", "", ""


def _brief_from_workshop(arguments: dict) -> dict | None:
    """The room's answer to IDEA's bar, from a sketch_idea_bar call.

    The same two functions that will read tonight's real proof do the work
    here, unchanged: `bar.read` composes the parts into one paragraph, and
    `bar.labels` counts which of the four came back. The model extracted; the
    server did the rest, and `parts` is arithmetic over the arguments rather
    than anything the model was asked to assert about itself.

    Both of the things the caller keeps come out of this one call — the keys
    the forecast counts and the prose the commit carries — so the meter on the
    builder's screen and the brief on their goal cannot describe different
    rooms. That is the reason this reads a sketch rather than the tiebreak:
    sketch_idea_bar is maintained through the conversation and catches a room
    that talks an idea through and never reaches a title.

    Only the four declared part keys are passed on. `bar.read` prefers a `text`
    argument when it is given one, and the schema does not declare one — so
    filtering here is what stops an undeclared argument from becoming the
    paragraph the coach is later told the builder said.

    None means nothing of the bar came back, which is every workshop that
    spent its turns on the tiebreak rather than on the body of the idea. That
    is a normal room, not a failure, and it leaves the goal exactly as it was
    before any of this existed.
    """
    given = {
        part.key: arguments.get(part.key) for part in bar.BAR[Phase.IDEA].parts
    }
    labels = bar.labels(Phase.IDEA, given)
    if not labels.parts:
        return None
    text = bar.read(Phase.IDEA, given).text.strip()
    if not text:
        return None
    return {
        # Trimmed to the same width a hand-written brief is held to: this lands
        # in a prompt block that has to stay a paragraph, and unlike an
        # accepted proof there is no row it would then disagree with.
        "text": text[:BRIEF_CHARS],
        "parts": labels.parts,
        "source": "WORKSHOP",
        "written_at": timezone.now().isoformat(),
    }


def _brief_from_proof(goal: Goal, checkin: CheckIn) -> dict | None:
    """The idea's body, written the one time IDEA's proof is accepted.

    None means leave the goal's brief exactly as it is, and there are four ways
    to get it. Three are "this is not that moment" — the verdict was not an
    accept, the evening was earned in some later phase, the row carries no text.
    The fourth is the one worth stating: **a brief the BUILDER wrote is never
    overwritten.** They may have written the idea in their own words before
    anything banked, and the proof arriving later does not get to replace what
    they said with what they filed.

    A brief the WORKSHOP wrote is replaced, and the distinction is the point.
    That one is a paragraph the coach composed out of a conversation, kept
    because it was better than the blank the goal used to carry — a sketch,
    made before anything was judged, and possibly covering two of the four
    parts. This one is the builder's own four-part answer, the only one the
    gate has ever accepted. When both exist the second is the founding
    statement of the idea and the first was standing in for it.

    Why this reads `pm_proof_text` rather than the four parts as fields: it
    cannot read them, and the reason is a rule rather than an omission. Every
    IDEA proof passes through `bar`, but `bar.labels()` returns which parts an
    answer satisfied and never their values — see the comment on
    `CheckIn.proof_parts`, which states the rule outright. The values are
    structured for exactly one turn, inside the suggest_proof arguments, and
    `bar.compose` turns them into prose before the row is written. So the whole
    of the idea, in the builder's own words, is the proof text; `parts` records
    which of the four the gate saw in it.

    The point of copying it onto the goal at all — the text is already on the
    check-in — is that the check-in's copy expires from the coach's view and
    this one does not. `_banked` sends the ten newest accepted proofs, trimmed
    to RECORD_CHARS; the IDEA proof is by construction the oldest row a goal has
    and the only four-part answer the product ever asks for, so it is both the
    first to fall off that list and the most likely to be cut in half while it
    is on it. The founding statement of the idea is the one row that must not
    age out of the prompt, and RECORD_LIMIT's own comment — "what falls off the
    end is the oldest, which is also the least likely to be re-asked for
    tonight" — is right about every row except this one.
    """
    if checkin.proof_status != CheckIn.ProofStatus.ACCEPTED:
        return None
    # The phase the evening was earned in, not the phase the goal is in now: a
    # verdict that advances the goal must still attribute its proof to IDEA.
    if (checkin.phase or goal.phase) != Phase.IDEA:
        return None
    if goal.brief and goal.brief.get("source") != "WORKSHOP":
        return None
    text = (checkin.pm_proof_text or "").strip()
    if not text:
        return None
    return {
        "text": text,
        "parts": list(checkin.proof_parts or []),
        "source": "PROOF",
        "written_at": timezone.now().isoformat(),
    }


def _labels_from_verdict(phase: str, payload: dict) -> bar.Labels | None:
    """The judge's own labels for the evening it just accepted — who it was
    about, and which parts of the bar it satisfied.

    Same division of labour as suggest_proof: the model extracts, the server
    counts. It is the call that already decides accept or push_back, so no new
    authority is handed out here — and what it says is filtered before it lands.
    An invented part key is dropped (bar.known_parts), because a gate that counts
    kinds must count names bar.py chose.

    None means "nothing usable came back", which is deliberately not the same as
    "empty". A verdict that flakes on this must not wipe the labels the draft
    already carried, and must never cost the builder the proof itself: the day
    is accepted either way, and an unlabelled accept simply leaves the kind still
    owed, which try_advance then names.
    """
    known = bar.known_parts(phase)
    parts = [key for key in bar._entries(payload.get("parts")) if key in known]
    subject = bar.normalise_subject(payload.get("subject") or "")
    if not parts and not subject:
        return None
    return bar.Labels(subject=subject, parts=parts)


def _react_to_proof(
    goal: Goal,
    checkin: CheckIn,
    image: bytes | None = None,
    content_type: str = "",
    pending_try: ProofAttempt | None = None,
) -> tuple[str, str, bar.Labels | None]:
    """LLM garnish with a deterministic floor (transcriber's fix_punctuation
    pattern): any failure logs and falls back to a stock reaction, so the daily
    loop never breaks because a model call flaked.

    That floor is "unjudged", not "accept". The loop surviving an outage is
    right and stays — the day is declared, proved, on the record, and in the
    streak. Banking a gate proof for it was a second, separate decision riding
    on the same word, and it handed the phase gate to whoever caught the model
    on a bad afternoon. Splitting them costs the builder nothing: filing again
    once the model answers gets the same evening a real reading, and until then
    the cycle stays open rather than closing on a verdict nobody gave.

    A screenshot, when there is one, is read by the vision model in this same
    call — one judgement over the text and the image together, because they
    are one claim about one day's work.

    Three things keep the judgement from moving under the builder. A
    resubmission is judged against every try already refused tonight and the
    words that refused each one; a COMPLETE proof Masterji drafted himself,
    filed unedited, is accepted without a model call at all; and his running
    notes go into the prompt so the evening cannot demand a fact the afternoon
    already took as given. The verdict is otherwise entirely the model's —
    nothing here passes work because the builder tried often enough.

    Two things bound what the model is deciding. It sees the proofs this goal has
    already banked, so a proof cannot be banked twice by being retold; and the
    submission arrives inside a fence with the rule that text in there is
    evidence and never instructions, because this is the one call in the product
    whose input the builder writes and whose output is a decision about them.
    """
    offer = checkin.proof_offer.strip()
    missing = checkin.proof_missing.strip()

    # Before anything else, including the draft shortcut below — a draft filed
    # unedited skips the model entirely, so a repeat that went through it would
    # be banked with nothing having read it at all.
    repeat = _already_banked(goal, checkin, checkin.pm_proof_text)
    if repeat is not None:
        logger.info(
            f"Proof on checkin {checkin.id} repeats accepted checkin {repeat.id}"
        )
        line = prompts.STOCK_DUPLICATE
        # "5 Aug", the same shape the record card shows (Masterji.tsx's
        # formatDate). Built rather than strftime'd because the format that
        # drops the leading zero is a platform extension, not a guarantee.
        return "push_back", line.format(date=f"{repeat.date.day} {repeat.date:%b}"), None

    if offer and not missing and checkin.pm_proof_text.strip() == offer:
        # He read the conversation, decided it cleared the bar, and wrote this
        # out himself. Asking him again could only produce a disagreement with
        # himself, and the builder would be the one who paid for it.
        #
        # `missing` is what makes that true, and why it is checked here. A
        # running draft is written down long before it clears anything, and it
        # is the same field — without this test, notes Masterji himself called
        # incomplete would file straight through untouched. That is not
        # leniency, it is the gate deciding nothing.
        logger.info(f"Proof filed from Masterji's own draft on checkin {checkin.id}")
        # No labels: the row already carries the draft's own, computed from the
        # arguments this very text was composed from (ChatView).
        return (
            "accept",
            prompts.STOCK_OFFER_ACCEPT,
            None,
        )

    # Written archive-before-overwrite by ProveView, so by the time we're here
    # the trail already holds tonight's rejected tries — oldest first (the
    # model's Meta orders by created_at).
    tries = list(checkin.attempts.all())
    # The try being replaced right now is handed in rather than read back,
    # because it is not saved yet — it commits with the row that replaces it,
    # so the record can never hold one without the other. Appended last
    # because this list is oldest first and it is tonight's most recent
    # refusal. `prior_tries` only reads `.text` and `.reaction`, so an unsaved
    # instance is the same thing to it as a row.
    if pending_try is not None:
        tries.append(pending_try)
    try:
        system = prompts.PROOF_REACTION_SYSTEM.format(
            # The standard the builder was shown, in the room that decides
            # whether they met it. Read out of guidance.PROOF_HINT, the same
            # module the check-in form, the gate refusal and the chat coach read
            # — so "that clears it" in the afternoon and the verdict at 11pm
            # cannot be answers to two different questions.
            judge_bar=prompts.judge_bar_for(Phase(goal.phase)),
            substance_rule=prompts.SUBSTANCE_RULE,
            respect_rule=prompts.RESPECT_RULE,
            label_rule=prompts.label_rule_for(Phase(goal.phase)),
            phase=goal.phase,
            declared=checkin.am_declaration,
            asked_for=prompts.PROOF_ASKED_FOR.format(proof_ask=checkin.proof_ask)
            if checkin.proof_ask
            else "",
            prior_try=prompts.prior_tries(tries),
            from_offer=prompts.from_draft(offer, missing),
            banked=prompts.record_block(
                _banked(goal, exclude=checkin), prompts.RECORD_FOR_JUDGE
            ),
            evidence_rule=prompts.EVIDENCE_NOT_INSTRUCTIONS,
        )
        if image:
            system += prompts.PROOF_IMAGE_RULE
        # Empty unless the server actually got an answer from the link.
        system += prompts.url_fact(checkin.url_alive)
        user_text = prompts.fence_submission(
            checkin.pm_proof_text, checkin.proof_url
        )
        # Both branches book to the same row, which is the point: a screenshot
        # does not make the evening a different evening, and the two prompts
        # here are the expensive ones in the product.
        with llm.attributing(ModelCall.Source.CHECKIN, checkin.id):
            raw = (
                # complete_with_image already reads LLM_VISION_MODEL, which
                # chains off the judge model — so both halves of this verdict
                # move together when the judge is upgraded.
                llm.complete_with_image(system, user_text, image, content_type)
                if image
                else llm.complete(system, user_text, model=settings.LLM_JUDGE_MODEL)
            )
        payload = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        verdict = payload.get("verdict", "")
        reaction = str(payload.get("reaction") or "").strip()
        if verdict not in ("accept", "push_back") or not reaction:
            # The model answered, but not the question it was asked. That is
            # the same state of knowledge as it never answering, so it gets the
            # same word — and it used to get "accept", which made a banked
            # proof reachable from any submission that knocked the reply off
            # its JSON: the proof text is the builder's own, and it goes into
            # this very call.
            #
            # A verdict with no words behind it lands here too. There is
            # nothing to say under an accept, and a push-back that cannot name
            # what is missing is the wasted evening PROOF_REACTION_SYSTEM
            # exists to forbid — so an unexplained verdict is treated as no
            # verdict rather than imposed in silence.
            logger.warning(f"Unreadable verdict {verdict!r} on checkin {checkin.id}")
            return "unjudged", prompts.STOCK_UNJUDGED, None
        return verdict, reaction, _labels_from_verdict(goal.phase, payload)
    except Exception as e:
        logger.error(f"Proof reaction failed: {e}")
        return "unjudged", prompts.STOCK_UNJUDGED, None
