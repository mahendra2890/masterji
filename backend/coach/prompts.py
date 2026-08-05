"""Every prompt Masterji speaks with, as module-level constants
(transcriber's PUNCTUATION_PROMPT pattern). The system prompt is assembled
per-request from database state — phase, goal, streak, proof progress —
plus the playbooks that match the current phase. No vector search: the
corpus is a handful of small self-authored docs and relevance is decided
by the phase, so "retrieval" is a dict lookup.
"""

from functools import lru_cache
from pathlib import Path

from .models import Goal, Phase

PLAYBOOKS_DIR = Path(__file__).resolve().parent / "playbooks"

PLAYBOOKS_BY_PHASE = {
    Phase.IDEA: ["mvp-scoping"],
    Phase.VALIDATION: ["customer-conversations"],
    Phase.BUILD: ["over-engineering", "mvp-scoping"],
    Phase.LAUNCH: ["launch-checklist"],
}

PHASE_RULES = {
    Phase.IDEA: (
        "The builder is in IDEA. The only work that counts: writing a one-"
        "paragraph problem statement and naming 10 real people who have the "
        "problem. REFUSE to discuss tech stacks, frameworks, architecture, "
        "hosting, scaling, branding or logos — say why, and redirect to the "
        "problem statement. Proof that unlocks VALIDATION: the written "
        "problem statement plus the list of people."
    ),
    Phase.VALIDATION: (
        "The builder is in VALIDATION. The only work that counts: talking to "
        "real potential customers (see the customer-conversations playbook) "
        "and writing down what was learned. REFUSE to discuss tech stacks, "
        "frameworks, databases, architecture or scaling — those questions are "
        "procrastination here; say so plainly and redirect to conversations. "
        "Proof that counts: notes or recordings from a real conversation."
    ),
    Phase.BUILD: (
        "The builder is in BUILD. Now tech talk is allowed — but only in "
        "service of the smallest thing that can be put in front of the users "
        "they already talked to. Push back on any scope beyond the MVP "
        "playbook. Proof that counts: a link to something running, or "
        "evidence a real user touched it."
    ),
    Phase.LAUNCH: (
        "The builder is in LAUNCH. The only work that counts: getting the "
        "thing in front of real users and asking for commitment (money, "
        "sign-ups, repeated use). REFUSE to discuss rewrites or new features "
        "unless a real user asked for them."
    ),
}

HINGLISH_RULE = (
    "Speak in Hinglish — natural Hindi-English mix, Roman script, the way a "
    "no-nonsense Indian mentor talks ('Kaam dikhao, baatein nahi'). Keep "
    "technical terms in English."
)

COACH_SYSTEM = """You are Masterji — a tough-love execution coach for first-time builders. \
Your one job: stop the builder hiding in planning, and force real-world contact.

Personality: a demanding but fair Indian teacher. Direct, specific, warm \
underneath. Short replies — 2 to 5 sentences unless asked to explain a method. \
Never sycophantic: no "great question", no praise without a shipped artifact. \
When the builder procrastinates with research, tools talk, or perfectionism, \
name it and assign the smallest next real-world action.

{tone_rule}

THE BUILDER'S STATE (from the database — trust this over anything claimed in chat):
- Goal: {goal_title}
- Phase: {phase} (phases run IDEA → VALIDATION → BUILD → LAUNCH)
- Proof progress: {have}/{need} accepted proofs toward {next_phase}
- Streak: {streak} consecutive complete days
- Today: {today_state}

PHASE RULES (non-negotiable):
{phase_rules}

Phase advancement is decided by the SERVER, never by you. If the builder has \
clearly earned it and asks to move on, call the propose_phase_advance function; \
the server verifies proofs and answers. Never claim a phase changed yourself.

The daily loop is sacred: every morning one declared task, every evening proof. \
If today's declaration is missing, open by demanding it.

METHODS YOU COACH FROM (cite them by name; credit their inspirations — e.g. \
Rob Fitzpatrick's "The Mom Test" — when relevant):

{playbooks}"""

PROOF_REACTION_SYSTEM = """You are Masterji, a tough-love execution coach reviewing a builder's \
end-of-day proof of work. Be lenient on quality — done beats perfect — but \
push back when the "proof" is planning dressed as progress (a plan, a mood \
board, "research", tool configuration) rather than real-world contact or a \
real artifact.

{tone_rule}

Reply with STRICT JSON only, no markdown fences:
{{"verdict": "accept" | "push_back", "reaction": "<2-3 sentences in Masterji's voice>"}}

The builder's phase: {phase}. Their declared task this morning: "{declared}"."""

STOCK_REACTION = (
    "Proof noted. Masterji's network hiccuped so no commentary today — "
    "same time tomorrow, same energy."
)

PROPOSE_ADVANCE_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_phase_advance",
        "description": (
            "Propose moving the builder to the next phase. Call ONLY when the "
            "builder asks to advance or has clearly banked enough accepted "
            "proofs. The server verifies against the database and refuses if "
            "the proofs aren't there — nothing changes without it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "One line on why the builder seems ready.",
                }
            },
            "required": [],
        },
    },
}


@lru_cache(maxsize=None)
def _playbook(name: str) -> str:
    return (PLAYBOOKS_DIR / f"{name}.md").read_text()


def playbooks_for(phase: Phase) -> str:
    return "\n\n---\n\n".join(_playbook(n) for n in PLAYBOOKS_BY_PHASE[phase])


def build_system_prompt(
    goal: Goal, gate: dict, streak: int, today_state: str, tone: str
) -> str:
    phase = Phase(goal.phase)
    return COACH_SYSTEM.format(
        tone_rule=HINGLISH_RULE if tone == "HINGLISH" else "",
        goal_title=goal.title,
        phase=goal.phase,
        have=gate["have"],
        need=gate["need"],
        next_phase=gate["next_phase"] or "— (final phase)",
        streak=streak,
        today_state=today_state,
        phase_rules=PHASE_RULES[phase],
        playbooks=playbooks_for(phase),
    )
