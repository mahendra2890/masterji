"""The week read back — computed from rows, never asked for.

The daily loop has no altitude control. A builder can complete seven honest
days and never see that the week moved the gate by zero, because the drift
`shipping-cadence.md` exists to prevent is only visible at weekly grain.

Two things this deliberately is not.

It is not a form. Every number here is arithmetic over check-ins the builder
already filed, which is the inverse of the weekly self-report the comparators
run on: nothing in this module asks for a figure, and there is no field for
one to be typed into.

And it is not a scheduled job. There is no scheduler on this deployment —
`render.yaml` declares one `type: web` service, Render's free plan has no
cron, and `.github/workflows/` has no `schedule:` trigger — so the digest is
computed on the first request of a new week and written then. A builder who
does not come back gets no digest, which is correct: there is nobody to read
it.

Counting and copy only. The row is written by `views._read_the_week_back`,
and that split is the one `streaks.py` already keeps: this half is testable
without a request.
"""

from datetime import date, timedelta

from . import guidance
from .models import CheckIn, Goal, PhaseTransition

DAYS = 7


def week_start(day: date) -> date:
    """The Monday of the week `day` falls in.

    Monday–Sunday rather than Sunday–Saturday, for two reasons that agree:
    `date.weekday()` already counts from Monday, and a week bounded that way
    puts the digest on a Monday — the morning where reading the last one back
    can still change what the next one holds.
    """
    return day - timedelta(days=day.weekday())


def summary(goal: Goal, start: date) -> dict:
    """What the seven days beginning `start` hold for this goal.

    Measured against `CheckIn.date`, which is the builder's own local date, and
    never against `created_at` — the same collision `streaks.span` documents.
    A window drawn on the server's UTC calendar would move a late-night proof
    into the wrong week for every builder ahead of UTC, which is most of them.

    `advanced_to` is the one exception and it is not fixable here: phase
    transitions carry only a server UTC timestamp, so a phase opened within a
    few hours of the boundary can land in the neighbouring week. It changes
    which Monday a builder is congratulated on and no count anywhere, so it is
    left standing rather than paid for with a column nothing else needs — the
    same trade `streaks.days_in_phase` names.
    """
    end = start + timedelta(days=DAYS - 1)
    rows = list(
        CheckIn.objects.filter(goal=goal, date__gte=start, date__lte=end).values(
            "date", "am_declaration", "pm_proof_text", "proof_status", "subject"
        )
    )
    accepted = [r for r in rows if r["proof_status"] == CheckIn.ProofStatus.ACCEPTED]
    # Declared AND proved, which is what `streaks.py` counts a run by. Counting
    # declarations would tell a builder who filed seven mornings and no evenings
    # that they had a complete week.
    complete = {r["date"] for r in rows if r["am_declaration"] and r["pm_proof_text"]}
    # Distinct, for the reason the gate is: three nights of notes about one
    # hostelmate are three days of honest work and one person's word. Unlike
    # `gates.accepted_proofs`, a BLANK subject is not counted as its own person
    # — there, a blank must never un-bank a proof accepted on its merits; here,
    # the sentence is "people spoken to", and IDEA's written problem statement
    # is not somebody spoken to.
    named = {r["subject"] for r in accepted if r["subject"]}
    moved = (
        PhaseTransition.objects.filter(
            goal=goal, created_at__date__gte=start, created_at__date__lte=end
        )
        .order_by("created_at")
        .last()
    )
    return {
        # Whether the week happened at all, and the only thing that decides
        # whether it is worth reading back. Not shown to anybody.
        "filed": len(rows),
        "days": len(complete),
        "accepted": len(accepted),
        "people": len(named),
        "advanced_to": moved.to_phase if moved else "",
    }


# What the builder reads on the first morning of a new week.
#
# In both tones, for the reason STOCK_OFFER_ACCEPT is: this one is on the happy
# path and it recurs, so a builder who asked to be spoken to in Hinglish would
# otherwise get an English wall every Monday for as long as they use the
# product.
#
# App voice, not Masterji's — it is written as a SYSTEM row (see Message.Role)
# because it is the product stating what the record holds, and stored as COACH
# it would come back to the model on the next turn as its own remembered words.
COPY = {
    "ENGLISH": {
        "head": "Last week, by the record: {facts}.",
        "days": "{days} of {total} days complete",
        "accepted": "{n} accepted toward the phase",
        "accepted_one": "1 accepted toward the phase",
        "none": "nothing accepted toward the phase",
        "people": "{people} spoken to",
        "moved": "and you opened {phase}",
        # Said only in the week this feature exists for: days on the record and
        # a gate that did not move. Not a scolding — the days were real and are
        # named first. It points at the aim of the proof, which is the thing
        # that was actually off.
        "flat": (
            " Days on the record and nothing banked yet — worth a look at what "
            "tonight's proof is pointed at."
        ),
    },
    "HINGLISH": {
        "head": "Pichhle hafte ka record: {facts}.",
        "days": "{total} mein se {days} din poore",
        "accepted": "{n} phase ke liye count hue",
        "accepted_one": "1 phase ke liye count hua",
        "none": "phase ke liye kuch count nahi hua",
        "people": "{people} se baat hui",
        "moved": "aur aapne {phase} khola",
        "flat": (
            " Din record par hain, par phase ke liye abhi kuch bank nahi hua — "
            "ek baar dekh lena ki aaj raat ka proof kis taraf ja raha hai."
        ),
    },
}


def _people(n: int, tone: str) -> str:
    """A person count, in the tone the builder asked to be spoken to in.

    English defers to `guidance.people`, which is the product's one English
    phrasing for this and is already quoted in two other places. Hinglish has
    no such helper because nothing else in the product counts people in it, so
    it is spelled here rather than by handing an English noun to a Hinglish
    sentence — which is what "2 people se baat hui" was.
    """
    if tone == "HINGLISH":
        return "1 aadmi" if n == 1 else f"{n} log"
    return guidance.people(n)


def digest(summary: dict, tone: str = "ENGLISH") -> str:
    """The week as the builder reads it.

    One short paragraph, and the shape is the constraint rather than a
    preference: this arrives as a SYSTEM row, which renders in a centred pill
    (`.systemMsg`) built for a single line. A list would come out as a run-on
    sentence in an oval. If this ever wants to be a list, that class needs a
    block variant first.

    The people clause is omitted when there is nobody to name rather than
    printed as a zero — a builder in IDEA has spoken to no one by design, and
    restating a phase's own bar is not this message's job.
    """
    copy = COPY.get(tone, COPY["ENGLISH"])
    facts = [copy["days"].format(days=summary["days"], total=DAYS)]
    if not summary["accepted"]:
        facts.append(copy["none"])
    elif summary["accepted"] == 1:
        # Spelled out rather than formatted, because Hinglish inflects the verb
        # on the count ("count hua" against "count hue") and a template with a
        # slot in it cannot say that.
        facts.append(copy["accepted_one"])
    else:
        facts.append(copy["accepted"].format(n=summary["accepted"]))
    if summary["people"]:
        facts.append(copy["people"].format(people=_people(summary["people"], tone)))
    if summary["advanced_to"]:
        facts.append(copy["moved"].format(phase=summary["advanced_to"]))
    text = copy["head"].format(facts=", ".join(facts))
    if summary["days"] and not summary["accepted"]:
        text += copy["flat"]
    return text
