"""The record as a file the builder can hand to someone.

Everything here is a rendering of rows that already exist. No number is
computed a second way for the file: the counts come from `gates` and `streaks`,
the same functions the dashboard and the closing card read, so a builder
holding this file and a reader holding the app cannot be told two things.

Three deliberate omissions, each for a reason the app itself doesn't have to
worry about:

- **No images.** Proof screenshots live in a private bucket and are signed on
  read; those links expire in minutes. A file kept for a placement interview
  that carries one is a file full of dead links, so the export records that a
  screenshot was filed and stops there.
- **No `subject`.** The counting key is normalised for arithmetic and is read
  by nothing that displays anything (see the field's comment in models.py).
  The person's name is in the builder's own proof text where they wrote it.
- **No coaching.** Playbook material, openers and hints are the product; the
  record is the builder's. A file that explains Masterji is a brochure.

Written oldest-first, unlike every screen, which shows the newest day at the
top. A dashboard is read for what happened yesterday; a document handed to
somebody is read from the beginning.
"""

from datetime import date

from . import gates, streaks
from .models import CheckIn, Goal, GoalRetirement, Phase


def _day(d: date) -> str:
    """"10 Aug 2026" — the same shape as the app's `formatDay`, which is what
    the builder has been reading their own record in all along."""
    return f"{d.day} {d:%b %Y}"


# What the verdict is called in a sentence. UNJUDGED is spelled out rather than
# softened: "the model was unreachable" is a real state, it is why the day
# counted without banking a proof, and a record that hid it would be claiming
# something the gate never granted.
VERDICT = {
    CheckIn.ProofStatus.ACCEPTED: "accepted",
    CheckIn.ProofStatus.PUSHED_BACK: "pushed back",
    CheckIn.ProofStatus.UNJUDGED: "filed, not read — Masterji was unreachable",
}


def _summary(goal: Goal, today: date) -> list[str]:
    accepted = gates.accepted_proofs_total(goal)
    contact = gates.contact_proofs(goal)
    # The start of the same span days_active is counted over, not
    # `goal.created_at`: a check-in can be dated earlier than the row that owns
    # it, and a file headed "Started 13 Aug" above a first entry dated the 9th
    # is a document that argues with itself in front of a stranger.
    started, _ = streaks.span(goal, today)
    return [
        f"- Started: {_day(started)}",
        f"- Phase reached: {Phase(goal.phase)}",
        f"- Days on the record: {streaks.days_active(goal, today)}",
        f"- Accepted proofs: {accepted}"
        + (f" — {contact} of them from real-world contact" if contact else ""),
        f"- Longest run of consecutive days: {streaks.best_streak(goal)}",
    ]


def _closing(retirement: GoalRetirement) -> list[str]:
    """How the record reads at the end, computed by `gates.reads_as` from earned
    proofs — never a label the builder chose. INVALIDATED is the one worth
    reading twice: it means real people said no, which is validation working."""
    return [
        "",
        "## How it ended",
        "",
        f"Closed {_day(retirement.created_at.date())} — "
        f"{retirement.get_outcome_display().lower()}, "
        f"and the record reads {gates.reads_as(retirement.goal, retirement.outcome)}.",
        "",
        f"> {retirement.reason}",
    ]


def _day_block(checkin: CheckIn) -> list[str]:
    out = [
        "",
        f"### {_day(checkin.date)} · {checkin.phase or '—'}",
        "",
        f"**Declared:** {checkin.am_declaration or '—'}",
    ]
    if checkin.declaration_fit == CheckIn.DeclarationFit.OFF_PHASE:
        # Advisory when it was given and advisory here: the day earned its proof
        # anyway, and the note is part of the honest record of the argument.
        out.append("")
        out.append("_Masterji called this off-phase for where the goal was._")
    if checkin.pm_proof_text or checkin.proof_status != CheckIn.ProofStatus.NONE:
        verdict = VERDICT.get(CheckIn.ProofStatus(checkin.proof_status))
        head = f"**Proof ({verdict}):**" if verdict else "**Proof:**"
        out.append("")
        out.append(f"{head} {checkin.pm_proof_text or '—'}")
    if checkin.proof_url:
        out.append("")
        out.append(f"Link filed: {checkin.proof_url}")
    if checkin.proof_image_key:
        out.append("")
        out.append(
            "A screenshot was filed with this proof. It is not included here — "
            "the app serves those over links that expire."
        )
    if checkin.coach_reaction:
        out.append("")
        out.append(f"Masterji: {checkin.coach_reaction}")
    attempts = list(checkin.attempts.all())
    if attempts:
        out.append("")
        out.append("Pushed back first:")
        for attempt in attempts:
            out.append("")
            out.append(f"- {attempt.text}")
            if attempt.reaction:
                out.append(f"  - Masterji: {attempt.reaction}")
    return out


def render(goal: Goal, today: date) -> str:
    """The whole file, as Markdown.

    Uncapped on purpose. `views.CHECKIN_HISTORY` is a budget for a payload sent
    on every dashboard load; this is a file the builder asked for once, and an
    export that quietly dropped a four-month goal's first weeks while calling
    itself the record would be the one failure this artifact cannot have —
    nobody checks a file for the days it is missing.
    """
    retirement = GoalRetirement.objects.filter(goal=goal).first()
    lines = [
        f"# {goal.title}",
        "",
        f"A Masterji record, exported {_day(today)}.",
        "",
        *_summary(goal, today),
        "",
        "Every proof below was filed against a task declared that morning, and "
        "the phases opened on a server count of accepted proofs — not on anyone "
        "saying the work was done. The tries that were pushed back are here too; "
        "they are what makes the rest of it worth reading.",
    ]

    transitions = list(goal.transitions.all())
    if transitions:
        lines += ["", "## The phases, as they opened", ""]
        lines += [
            f"- {t.from_phase} → {t.to_phase} · {_day(t.created_at.date())}"
            for t in transitions
        ]

    # Oldest first — see the module docstring. `.all()` rather than a slice: the
    # queryset's default ordering is newest-first for the screens.
    checkins = list(goal.checkins.prefetch_related("attempts").all())[::-1]
    if checkins:
        lines += ["", "## The days"]
        for checkin in checkins:
            lines += _day_block(checkin)

    if retirement:
        lines += _closing(retirement)

    return "\n".join(lines) + "\n"


def filename(goal: Goal, today: date) -> str:
    """`masterji-tiffin-app-2026-08-13.md`.

    Slugged rather than quoted: a goal title is free text and a builder who
    typed a slash into theirs must not get a filename with a path separator in
    it. `Content-Disposition` is also the one header where a stray quote or
    newline from user input would be worth worrying about.
    """
    slug = "".join(c if c.isalnum() else "-" for c in goal.title.lower())
    slug = "-".join(part for part in slug.split("-") if part)[:60].strip("-")
    return f"masterji-{slug or 'record'}-{today.isoformat()}.md"
