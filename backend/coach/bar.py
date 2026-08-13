"""What ONE night's evidence has to contain — as parts the server can count,
not prose the model has to judge.

guidance.PROOF_HINT says the same bar to the BUILDER, in a sentence. This says
it to the SERVER, in pieces, and the difference is who does the counting.
VALIDATION asks for "3 things they said in their own words", and until this
module existed the only thing that could decide whether an answer held three
was the model reading its own paragraph back. It got that wrong exactly the way
you would expect: a builder named three of them in one sentence, was told
"that's one usable line, not three", and was asked for all of it again twice.

So suggest_proof stopped taking a paragraph plus the model's own verdict on it,
and started taking the parts. A model that has to emit ["…", "…", "…"] cannot
round three down to one — there is no prose left to hide the miscount in — and
what is still owed becomes len() and a subtraction in read(), done here, in
code the model does not get a vote in.

What this does NOT do is decide whether the day counted. A short list keeps the
one-tap filing shut and shows the builder what is still owed; filing is still
theirs, the evening's judgement is still the model's (views._react_to_proof
tells it to judge on the merits), and a real conversation that yielded two good
quotes is still accepted when it is filed. gates.py counts accepted check-ins
and has never read a word of this.
"""

from typing import NamedTuple

from .models import Phase


class Part(NamedTuple):
    """One piece of tonight's evidence."""

    # The suggest_proof argument the model fills in.
    key: str
    # What the builder is shown when this piece is still owed. Their terms, not
    # ours — it lands verbatim in the "Still needed tonight" list under Today.
    label: str
    # What the model is told the argument is for.
    ask: str
    # How many entries clear it. Above 1 makes the part a LIST in the tool
    # schema, which is the whole point of this module: "three things" is a
    # length, not an opinion about how a sentence was punctuated.
    need: int = 1
    # The label when exactly one entry is still owed — "1 more things they
    # said" reads like a bug, because it is one.
    one_label: str = ""


class Bar(NamedTuple):
    parts: tuple[Part, ...]
    # Every part, or any one of them. VALIDATION wants the whole of one
    # conversation; BUILD takes a link OR evidence someone touched it, and
    # demanding both would be a bar the playbook never set.
    every: bool = True
    # What an any-of bar owes while it has nothing at all. Written out rather
    # than joined from the labels because "or" is the whole meaning of it.
    either_label: str = ""
    # Which part names the PERSON this evening's evidence is about, when the
    # phase has one. gates.py counts distinct values of it rather than rows, so
    # the module that decides what a part means is also the module that says
    # which part is an identity — the alternative is gates.py hardcoding the
    # string "who", which is bar.py's business leaking one file over.
    subject_key: str = ""


BAR = {
    Phase.IDEA: Bar(
        parts=(
            Part(
                key="problem",
                label="the problem in a paragraph — who has it, what they do "
                "about it today, and why that's bad",
                ask="The problem statement in their words: who has this "
                "problem, what they do about it today, and why that is bad.",
            ),
            Part(
                key="place",
                label="one specific place these people already are",
                ask="The one place these people are already gathered, "
                "specific enough to have an address or a name. A channel "
                "('Reddit', 'LinkedIn') is not a room and does not count.",
            ),
            Part(
                key="why_there",
                label="why you think they're there",
                ask="Why the builder believes those people are there — what "
                "they have seen, not what they assume.",
            ),
            Part(
                key="first_conversation",
                label="how you'd get one conversation this week",
                ask="How they would get one conversation out of that place "
                "this week. Still desk work: no outreach happens in IDEA.",
            ),
        )
    ),
    Phase.VALIDATION: Bar(
        parts=(
            Part(
                key="who",
                label="who you spoke to",
                ask="Who the builder spoke to — name or role, and anything "
                "that places them.",
            ),
            Part(
                key="quotes",
                label="things they said in their own words",
                one_label="thing they said in their own words",
                need=3,
                ask="Things the person said, IN THEIR OWN WORDS — one entry "
                "per thing. Several said in one breath are several entries: "
                "split them here rather than judging whether a sentence "
                "counted as one. Never merge two into a summary, and never "
                "write one they did not say.",
            ),
            Part(
                key="last_action",
                label="what they last did about this problem",
                ask="What the person last actually DID about the problem — "
                "the workaround, the thing they tried, the thing that failed. "
                "Not what they said they would do.",
            ),
            Part(
                key="commitment",
                label="the commitment you asked for, and whether you got it",
                ask="What the builder asked this person to give up — time, "
                "an intro, a look at their books, a next meeting — and "
                "whether they got it. Praise for the idea is not a "
                "commitment.",
            ),
        ),
        subject_key="who",
    ),
    Phase.BUILD: Bar(
        parts=(
            Part(
                key="link",
                label="a link to something running",
                ask="A link to the thing running.",
            ),
            Part(
                key="touched",
                label="evidence a real user touched it",
                ask="Evidence a real user touched it — what they did, when, "
                "and whether anyone asked them to.",
            ),
        ),
        every=False,
        either_label="a link to something running, or evidence a real user touched it",
    ),
    Phase.LAUNCH: Bar(
        parts=(
            Part(
                key="link",
                label="a link to your public post",
                ask="A link to the public post.",
            ),
            Part(
                key="action",
                label="evidence of a stranger's action or payment",
                ask="What a stranger actually did — signed up, paid, came "
                "back — with the number if there is one.",
            ),
            Part(
                key="rejection",
                label="a real rejection, with the reason they gave",
                ask="A real rejection and the reason the person gave for it. "
                "A no with a reason is evidence; a no with no reason is not.",
            ),
        ),
        every=False,
        either_label="a link to your public post, a stranger's action or payment, "
        "or a real rejection with the reason they gave",
    ),
    Phase.TRACTION: Bar(
        parts=(
            Part(
                key="returned",
                label="a stranger who came back on their own",
                ask="The same stranger coming back: what they did the second "
                "time, when, and that nobody asked them to. Two different "
                "people using it once each is not this — the whole point is "
                "the SAME person returning.",
            ),
            Part(
                key="paid",
                label="a payment — who, how much, what for",
                ask="Who paid, how much in ₹, and what for. A promise to pay "
                "is not a payment; the money has to have moved.",
            ),
        ),
        every=False,
        either_label="a stranger who came back on their own, or a payment — "
        "who paid, how much, and what for",
    ),
}


class Draft(NamedTuple):
    """A suggest_proof call, as the two fields the check-in stores."""

    text: str
    missing: str


def _entries(value) -> list[str]:
    """One tool argument as a clean list, whatever shape it arrived in.

    Tool arguments are model-authored JSON: a list part can come back as a bare
    string, a single part as a one-element list, and either can carry blanks
    and padding. Normalising here is what lets read() below do nothing but
    count. llm._tool_arguments already guarantees a dict, so this is the last
    place a surprise can get in.
    """
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [entry for entry in (str(item).strip() for item in items) if entry]


def _owed(part: Part, have: int) -> str:
    """What to call a part that isn't there yet, with the arithmetic done.

    The subtraction is the point. "Give me three things he said" to a builder
    who has already given two is the sentence that made them retype all three.
    """
    if part.need == 1:
        return part.label
    if not have:
        return f"{part.need} {part.label}"
    short = part.need - have
    if short == 1 and part.one_label:
        return f"1 more {part.one_label}"
    return f"{short} more {part.label}"


def compose(bar: Bar, given: dict[str, list[str]]) -> str:
    """The parts as one paragraph, for a call that sent them without prose.

    A deterministic floor in the house style: the draft the builder reads must
    never be empty because the model spent its whole answer on the structure.
    Flat on purpose — the model's own wording is better whenever it sends one,
    and this only has to be true.
    """
    return " ".join(
        f"{part.label.capitalize()}: {'; '.join(given[part.key])}."
        for part in bar.parts
        if given[part.key]
    )


class Labels(NamedTuple):
    """What an accepted proof turns out to be about, as the gate counts it."""

    # bar.Bar.subject_key's value, normalised for counting. Blank when the phase
    # has no identity part, or when nothing came back for it.
    subject: str
    # The part keys this evidence satisfied, in bar order.
    parts: list[str]


def normalise_subject(value: str) -> str:
    """A person's name as a counting key, not as prose.

    Case-folded and whitespace-collapsed so "Priya " and "priya" are one
    person, and truncated to the field's width. Deliberately crude: this is not
    identity resolution, and it does not try to be. "Priya" and "Priya S." stay
    two people, because the alternative is a server guessing that two names
    mean one person and silently costing a builder a proof for it.
    """
    return " ".join(str(value or "").split()).casefold()[:120]


def labels(phase: str, arguments: dict) -> Labels:
    """A suggest_proof call, as the two facts the gate will count later.

    Same normalisation as read(), same source, no second opinion: the model
    extracted the parts when it drafted the proof, and this is arithmetic over
    what it sent. Which parts are present is a truth about the arguments, so it
    is computed here rather than asked for.
    """
    bar = BAR[Phase(phase)]
    given = {part.key: _entries(arguments.get(part.key)) for part in bar.parts}
    subject = ""
    if bar.subject_key:
        entries = given.get(bar.subject_key) or []
        subject = normalise_subject(entries[0] if entries else "")
    return Labels(
        subject=subject, parts=[part.key for part in bar.parts if given[part.key]]
    )


def known_parts(phase: str) -> list[str]:
    """Every part key this phase's bar defines — what a label may legally say.

    The judge is asked for part keys, and a model asked for keys will sometimes
    invent one. An unknown key is dropped rather than stored, so a gate that
    counts kinds is counting names this module chose.
    """
    return [part.key for part in BAR[Phase(phase)].parts]


def label_for(phase: str, key: str) -> str:
    """What to call one part in a sentence the builder reads."""
    for part in BAR[Phase(phase)].parts:
        if part.key == key:
            return part.label
    return key


def read(phase: str, arguments: dict) -> Draft:
    """A suggest_proof call, counted.

    `missing` is computed here and is never the model's to assert: it is which
    parts came back empty and, for a list part, how many entries short it is.
    That is the whole transfer this module exists to make — the model extracts,
    the server counts.
    """
    bar = BAR[Phase(phase)]
    given = {part.key: _entries(arguments.get(part.key)) for part in bar.parts}
    if bar.every:
        owed = [
            _owed(part, len(given[part.key]))
            for part in bar.parts
            if len(given[part.key]) < part.need
        ]
    else:
        owed = [] if any(given.values()) else [bar.either_label]
    text = str(arguments.get("text") or "").strip() or compose(bar, given)
    # Nothing given at all is not a draft owing everything — it is a call that
    # said nothing, and views drops it. Reporting the whole bar as missing here
    # would write an empty draft onto the check-in with a full complaint under
    # it, for a turn in which the builder said nothing to bank.
    return Draft(text=text, missing="; ".join(owed) if text else "")
