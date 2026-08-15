"use client";

// Coach API client (journal-api pattern from the portfolio): one request()
// with a timeout, a 401→refresh→replay retry, DRF error surfacing, and
// snake_case → camelCase mappers at the boundary. The two live turns are the
// exception — they stream NDJSON, and they share one opener and one reader
// (`streamTurn` below, over `lib/ndjson.ts`) rather than a copy each.

import { API_URL } from "@/lib/auth-client";
import { filenameFrom } from "./download";
import { ndjsonFeed } from "./ndjson";
import { refusalFrom } from "./refusal";

const TIMEOUT_MS = 15000;

/** An HTTP-level refusal (4xx/5xx). Network failures stay plain Errors,
 * so callers can tell "retry later" from "retrying won't help". */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number
  ) {
    super(message);
  }
}

export type Phase =
  | "IDEA"
  | "VALIDATION"
  | "BUILD"
  | "LAUNCH"
  | "TRACTION";

export type Goal = {
  id: number;
  title: string;
  phase: Phase;
  status: string;
  createdAt: string;
  /** Whether the record now points at this wording. Sharpening it is free until
   * the first proof is banked and refused after — the same count the server
   * checks, sent so the control appears exactly while it would be accepted.
   * Defaulted true for a browser holding a payload older than the field: not
   * offering an edit is the safe half of that guess. */
  titleLocked: boolean;
  /** The idea itself, as opposed to its headline — the builder's own words from
   * the evening IDEA was cleared, or what they wrote before anything banked.
   * Empty string until something has written one, which is every goal created
   * before this field existed. */
  brief: string;
  /** The one-liners parked in the workshop this goal came out of — everything
   * that room was choosing between, including whichever one became this. Empty
   * for a goal typed without a room, and for every goal older than the field. */
  considered: string[];
};

// `owed` is the KINDS of evidence the phase still has none of, already worded
// for the builder (the server reads bar.py's own labels). Empty on every phase
// that only counts rows. It is separate from have/need because it is a different
// shape of shortfall: a full count with something still owed is a real state,
// and the meter must not read it as earned.
// `banked` is the accepted rows behind `have`. On VALIDATION `have` counts
// people, so three nights about one hostelmate read 1/3 — true, and unreadable
// without the other number beside it.
export type Gate = {
  have: number;
  need: number;
  nextPhase: Phase | null;
  owed: string[];
  banked: number;
};

export type PhaseTransition = {
  fromPhase: Phase;
  toPhase: Phase;
  /** One line, in the builder's words, on what this phase would produce —
   * asked once when the phase unlocked. "" when they skipped it, which is a
   * legal and common state: nothing about the gate reads this. */
  intent: string;
  createdAt: string;
};

/** A proof submission Masterji pushed back, kept when the builder answered
 * it with a new one. The check-in's own fields are always the CURRENT
 * proof; these are the tries before it, oldest first. */
export type ProofAttempt = {
  id: number;
  text: string;
  url: string;
  /** This app's address for the screenshot; "" when the try had no image.
   * Same contract as `CheckIn.proofImageUrl` — see there. */
  imageUrl: string;
  reaction: string;
  createdAt: string;
};

export type CheckIn = {
  id: number;
  date: string; // YYYY-MM-DD, from the CLIENT's local clock
  phase: Phase | ""; // stamped server-side; "" only for pre-migration rows
  amDeclaration: string;
  /** The hour the builder said tonight's proof would land, 0-23 on their own
   * clock, or null because naming one is optional. Voice, never gate: nothing
   * counts it, nothing refuses a proof for arriving after it, and no
   * notification is promised on it. It is on the record so the coach can hold
   * them to their own word. */
  dueHour: number | null;
  /** Whether this morning's task is the work the phase is for. Advisory —
   * an off-phase task is still allowed and still earns its proof.
   * UNJUDGED means the model was unreachable, not that it passed. */
  declarationFit: "UNJUDGED" | "ON_PHASE" | "OFF_PHASE";
  declarationReaction: string;
  /** The same task, rewritten to answer the reaction above it — an offer that
   * fills the declare box, never a correction anyone is held to. Empty whenever
   * the reaction is: a sharpening under no complaint is a fix for a problem the
   * builder was never told they had. Declaring it re-runs the judgement, so the
   * model never grades wording it handed itself. */
  sharpened: string;
  /** What tonight's proof must show for THIS task. Empty when unjudged —
   * fall back to the phase's static ask in CoachState.guidance. */
  proofAsk: string;
  /** Tonight's proof as Masterji has it so far, written from work the builder
   * described in chat and rewritten each time another piece arrives. An offer,
   * not a record — nothing counts until they file it. */
  proofOffer: string;
  /** What that draft still lacks, one phrase per piece, semicolon-separated.
   * Empty means it clears the phase's bar — and only then does filing it
   * unedited skip the evening's judgement. Non-empty makes it notes: proof of
   * being heard, and the whole of what Masterji may still ask for tonight. */
  proofMissing: string;
  /** Today's reading as Masterji heard the builder say it, waiting to fill the
   * number box on the evening form — the number half of `proofOffer`, and an
   * offer on the same terms. null whenever no figure was said, which is most
   * evenings; zero is a number somebody counted and is not that. Nothing is
   * recorded until they file: `metricValue` is the reading, this is not. */
  metricOffer: number | null;
  pmProofText: string;
  proofUrl: string;
  /** This app's address for the screenshot backing this proof — put it in an
   * <img src> and the server signs a short-lived link and redirects. Not a
   * credential itself, and not shareable: it needs the reader's own session.
   * "" when there's no image or storage isn't configured. */
  proofImageUrl: string;
  /** UNJUDGED is filed-but-unread: the model was unreachable when it landed.
   * The day counts — record and streak — but nothing is banked toward the
   * phase, and the cycle stays open so filing again gets it a real reading. */
  proofStatus: "NONE" | "ACCEPTED" | "PUSHED_BACK" | "UNJUDGED";
  coachReaction: string;
  /** This day's reading of the one number the builder watches, or null — which
   * is almost every row, since the number is only ever asked for at TRACTION.
   * Zero is a real reading and must not be treated as absent. */
  metricValue: number | null;
  /** What that number was CALLED on this day, stamped when the reading was
   * written and never rewritten. After a rename this disagrees with the goal's
   * current metric name, and this one is the true thing about this evening —
   * which is what makes renaming a recorded slip rather than a silent
   * relabelling of the whole series. */
  metricLabel: string;
  attempts: ProofAttempt[];
};

export type ChatMessage = {
  id: number;
  /** SYSTEM is the app talking about the conversation rather than a turn in
   * it — today only "that one didn't go through". It is stored server-side so
   * it survives the refetch that ends every turn, and it is kept out of what
   * the model is shown. The log has to draw it as something other than the
   * coach speaking. */
  role: "USER" | "COACH" | "SYSTEM";
  /** Which kind of app-voice row this is, read only when `role` is SYSTEM.
   * NOTICE is a turn that didn't land and carries the retry; DIGEST is the
   * week read back on the first visit of a new one, and must not — the turn
   * above it is unrelated and could be days old. Defaults to NOTICE for rows
   * written before the field existed, which were all notices. */
  kind: "NOTICE" | "DIGEST";
  content: string;
  /** The phase the conversation was in when this was said, stamped server-side
   * and never rewritten. "" only for rows written before the field existed. */
  phase: Phase | "";
  createdAt: string;
};

export type Retirement = {
  id: number;
  /** The closed goal's id — used to fetch its day-by-day record. */
  goalId: number;
  title: string;
  outcome: "ABANDONED" | "COMPLETED";
  /** Derived server-side from earned proofs — never self-reported. Closing is
   * never blocked; this is what the record honestly says about it. */
  readsAs: "ACHIEVED" | "UNVERIFIED" | "INVALIDATED" | "UNTESTED";
  reason: string;
  phaseReached: Phase;
  /** Every accepted proof banked — what the builder actually did. */
  acceptedProofs: number;
  /** The VALIDATION-onward subset; only qualifies the INVALIDATED reading. */
  contactProofs: number;
  daysActive: number;
  bestStreak: number;
  coachReaction: string;
  createdAt: string;
  /** The public link's slug, or null while the record is private — which is
   * the default and the state every record starts in. Only ever sent to the
   * owner; the public page has no idea an owner exists. */
  shareSlug: string | null;
};

/** One closed goal, as a stranger holding the link may read it. Computed
 * facts only — the verdict, the counts, the phase timeline — and never the
 * builder's prose: not the reason they closed it, not a proof text, not a
 * check-in, not their name. Off by default and revocable. */
export type SharedRecord = {
  title: string;
  outcome: "ABANDONED" | "COMPLETED";
  /** Computed from earned proofs by the server, never self-reported. */
  readsAs: "ACHIEVED" | "UNVERIFIED" | "INVALIDATED" | "UNTESTED";
  phaseReached: Phase;
  acceptedProofs: number;
  /** The VALIDATION-onward subset — the ones that needed a real person. */
  contactProofs: number;
  daysActive: number;
  bestStreak: number;
  startedOn: string;
  closedOn: string;
  timeline: { toPhase: Phase; on: string }[];
};

/** Per-phase builder-facing copy, served rather than duplicated here: the
 * backend owns these strings because gates.py is what actually enforces
 * them, and a second copy in the client is a promise nothing keeps. */
export type Guidance = {
  phaseHint: string;
  proofHint: string;
  proofExamples: string[];
  /** Things to say to Masterji, offered while the chat log is still empty.
   * Phase-shaped, and the server's to write for the same reason the rest of
   * this bundle is. */
  openers: string[];
};

/** The room before the goal — a metered vestibule, never a phase.
 *
 * Present only on the no-goal screen, and only once the builder has said
 * something: reading state never opens a room, because a workshop is a turn
 * budget and one should exist because somebody started talking. */
export type Workshop = {
  id: number;
  /** Which of the two rooms this is: the one before the goal, or the one
   * reopened once per goal after it. Sent by the server rather than inferred
   * from whether there are candidates — an empty first room has none either. */
  status: "OPEN" | "REOPENED" | "SPENT";
  /** One-liners parked so far, oldest first. Capped server-side. */
  candidates: string[];
  maxCandidates: number;
  /** What the coach's tiebreak landed on. Fills the commit box; commits
   * nothing — the same bargain the goal examples make. */
  suggestedTitle: string;
  turnsUsed: number;
  turnsTotal: number;
  /** Computed by the server, not here, so the meter on screen and the
   * refusal from the server can never disagree about what is left. */
  turnsLeft: number;
  /** How much of IDEA's bar this conversation has already turned up. */
  sketch: WorkshopSketch;
  messages: WorkshopMessage[];
};

/** The pre-commit forecast: what committing would cost, in the phase's own
 * four parts. Every field of it is the server's arithmetic — `have` is a
 * count of part keys and `owed` is the subtraction, both done there, because
 * a client doing its own is a second answer waiting to disagree with the one
 * the coach was given. It is a forecast and never a gate: nothing is banked
 * here, and IDEA's one proof is still filed and judged after the commit. */
export type WorkshopSketch = {
  /** IDEA's part keys the room has turned up — keys, never the values. */
  parts: string[];
  have: number;
  need: number;
  /** The parts still open, in the builder's words rather than as keys. */
  owed: string[];
  /** The whole bar in order, each part with whether it has landed — what the
   * room's scaffold stands up from turn zero, before anything has surfaced.
   *
   * The same four facts `have`/`owed` carry, in the shape a list renders from.
   * The labels are the server's because bar.py owns them: a second wording of
   * IDEA's questions here would drift from the one the evening is judged
   * against, and this screen is where a builder reads them first. */
  asks: { key: string; label: string; have: boolean }[];
};

export type WorkshopMessage = {
  id: number;
  role: "USER" | "COACH" | "SYSTEM";
  content: string;
  createdAt: string;
};

export type CoachState = {
  goal: Goal | null;
  gate: Gate | null;
  /** Null only on the no-goal screen, which has no phase to speak about. */
  guidance: Guidance | null;
  /** Whether object storage is wired. False hides the upload control, so an
   * unconfigured deploy never offers something it can't accept. */
  uploadsEnabled: boolean;
  streak: number;
  /** The longest complete run this goal ever had. Shown beside a broken
   * streak so a zero doesn't read as "none of it happened". */
  bestStreak: number;
  /** Days since the current phase opened, measured on the server against the
   * date this request sent. Never computed here: the coach is handed the same
   * subtraction in its state block, and a number the builder reads that
   * disagrees with the number the coach is holding is the exact failure this
   * being server-side prevents. 0 on the day a phase opens. */
  daysInPhase: number;
  today: CheckIn | null;
  /** Today's task as Masterji heard it in chat, waiting to fill the declare
   * box — the morning's mirror of `CheckIn.proofOffer`. Top-level rather than
   * on `today` because at the moment it is written there is no check-in: an
   * offer is what there is INSTEAD of one. "" once anything is declared, and
   * "" again tomorrow, since the server only serves a draft stamped with the
   * date this request sent. */
  declarationOffer: string;
  checkins: CheckIn[];
  /** How many days the goal actually has, which is not always how many arrived:
   * this payload is capped, and the record card's "Show all N" used to count the
   * rows it was handed. On a goal past the cap that offered all ninety of
   * ninety-five, with no sign the other five existed. When this is larger than
   * `checkins.length`, the rest come from `getGoalHistory`. */
  checkinsTotal: number;
  transitions: PhaseTransition[];
  messages: ChatMessage[];
  phases: Phase[];
  /** Finishing is the expected move here — affects prominence only, never
   * permission: closing an achieved goal works from any phase. */
  atFinishLine: boolean;
  /** Retired goals, newest first — the record that outlives each idea. */
  archive: Retirement[];
  /** Days declared-and-proved across every goal, so retiring an idea doesn't
   * erase the fact that the work happened. */
  lifetimeDays: number;
  tone: "ENGLISH" | "HINGLISH";
  /** Which side of the table the coach sits on. THINKING makes him a thinking
   * partner in chat — questions and options instead of assignments — and
   * changes nothing about the gate. */
  mode: "COACH" | "THINKING";
  /** Null while a goal is active (the room is shut then, by design) and until
   * the builder's first turn in it. */
  workshop: Workshop | null;
  /** Composer-fillers for the workshop, the server's to write for the same
   * reason the phase openers are. */
  workshopOpeners: string[];
  /** The room's whole turn budget, sent even when no room is open yet so the
   * meter can be read before the first turn is spent. */
  workshopTurns: number;
  /** The day they said they'd launch, if they said one. Null until then —
   * there is no default date, because a date the app picked is not a
   * commitment anybody made. */
  launch: LaunchDate | null;
  /** Whether naming one is available yet. BUILD onward: a launch date on a
   * goal with no artifact is a wish. */
  canSetLaunch: boolean;
  /** launch-checklist.md's ladder, served rather than copied here — the
   * playbook owns the rungs and a second copy would drift. */
  ponds: { value: string; label: string }[];
  /** The one number they chose to watch, and every reading of it. Null until
   * they name one: there is no default metric, because a number the app picked
   * is not one anybody decided to watch. */
  metric: Metric | null;
  /** Whether naming one is available. TRACTION only, and read off the PHASE
   * rather than off arriving in it — TRACTION is the end of the ladder, so a
   * builder already standing there has no advance left for an invitation to
   * ride in on. */
  canSetMetric: boolean;
};

/** A launch date and its slip trail. Every number is the server's arithmetic
 * over append-only rows: moving the date writes another one, so what the
 * record holds is "declared the 24th, moved once, currently the 26th" rather
 * than just the answer. No gate reads any of it — the visible trail is the
 * whole of the consequence. */
export type LaunchDate = {
  date: string;
  pond: string;
  pondLabel: string;
  /** Negative once the day has been. Which refuses nothing. */
  daysOut: number;
  /** Moves, not rows: naming one for the first time is not a slip. */
  moves: number;
  first: string;
};

/** The one number the builder watches at TRACTION, and its readings.
 *
 * launch-checklist.md's "One metric. Pick the single number that means 'someone
 * got the value'... and watch only that", finally held by the server. No gate
 * reads any of it: a number that falls refuses nothing, costs no proof and
 * breaks no streak. It is a scoreboard, not a bar. */
export type Metric = {
  name: string;
  /** Oldest first, capped server-side. Each reading carries the name it was
   * taken under, so a series with a seam in it shows the seam. */
  series: { date: string; value: number; label: string }[];
  /** How many readings exist in total, which is more than `series.length` once
   * a goal has been at TRACTION a long time. */
  held: number;
  /** How many times they changed what they were counting, measured between two
   * readings — so a rename with nothing counted under the old name leaves no
   * mark, because nothing slipped. */
  swaps: number;
};

/* --- server shapes ------------------------------------------------------ */

type ServerGoal = {
  id: number;
  title: string;
  phase: Phase;
  status: string;
  created_at: string;
  title_locked?: boolean;
  brief?: { text?: string } | null;
  considered?: string[] | null;
};
type ServerGate = {
  have: number;
  need: number;
  next_phase: Phase | null;
  owed?: string[];
  banked?: number;
};
type ServerTransition = {
  from_phase: Phase;
  to_phase: Phase;
  intent?: string;
  created_at: string;
};
type ServerRetirement = {
  share_slug?: string | null;
  id: number;
  goal: number;
  title: string;
  outcome: Retirement["outcome"];
  reads_as: Retirement["readsAs"];
  reason: string;
  phase_reached: Phase;
  accepted_proofs: number;
  contact_proofs: number;
  days_active: number;
  best_streak: number;
  coach_reaction: string;
  created_at: string;
};
type ServerCheckIn = {
  id: number;
  date: string;
  phase: Phase | "";
  am_declaration: string;
  due_hour?: number | null;
  declaration_fit?: CheckIn["declarationFit"];
  declaration_reaction?: string;
  sharpened?: string;
  proof_ask?: string;
  proof_offer?: string;
  proof_missing?: string;
  metric_offer?: number | null;
  pm_proof_text: string;
  proof_url: string;
  proof_image_url?: string;
  proof_status: CheckIn["proofStatus"];
  coach_reaction: string;
  metric_value?: number | null;
  metric_label?: string;
  attempts?: {
    id: number;
    text: string;
    url: string;
    image_url: string;
    reaction: string;
    created_at: string;
  }[];
};
type ServerMetric = {
  name: string;
  series?: { date: string; value: number; label?: string }[];
  held?: number;
  swaps?: number;
};

/** One shape, two callers — the state payload and the endpoint that names the
 * metric both return it, and a second copy of this mapping is a second chance
 * for the record card and the control to disagree about the same series. */
const fromServerMetric = (m: ServerMetric | null): Metric | null =>
  m && {
    name: m.name,
    series: (m.series ?? []).map((r) => ({
      date: r.date,
      value: r.value,
      label: r.label ?? m.name,
    })),
    held: m.held ?? (m.series ?? []).length,
    swaps: m.swaps ?? 0,
  };

type ServerMessage = {
  id: number;
  role: "USER" | "COACH" | "SYSTEM";
  kind?: "NOTICE" | "DIGEST";
  content: string;
  phase?: Phase | "";
  created_at: string;
};
type ServerWorkshopMessage = {
  id: number;
  role: "USER" | "COACH" | "SYSTEM";
  content: string;
  created_at: string;
};
type ServerWorkshop = {
  id: number;
  status?: "OPEN" | "REOPENED" | "SPENT";
  candidates?: string[];
  max_candidates?: number;
  suggested_title?: string;
  turns_used?: number;
  turns_total?: number;
  turns_left?: number;
  sketch?: {
    parts?: string[];
    have?: number;
    need?: number;
    owed?: string[];
    asks?: { key: string; label: string; have: boolean }[];
  };
  messages?: ServerWorkshopMessage[];
};

const fromServerWorkshop = (w: ServerWorkshop): Workshop => ({
  id: w.id,
  status: w.status ?? "OPEN",
  candidates: w.candidates ?? [],
  maxCandidates: w.max_candidates ?? 3,
  suggestedTitle: w.suggested_title ?? "",
  turnsUsed: w.turns_used ?? 0,
  turnsTotal: w.turns_total ?? 0,
  turnsLeft: w.turns_left ?? 0,
  sketch: {
    parts: w.sketch?.parts ?? [],
    have: w.sketch?.have ?? 0,
    need: w.sketch?.need ?? 0,
    owed: w.sketch?.owed ?? [],
    // Defaulted like the rest. Empty means the scaffold draws nothing, which
    // is exactly the pre-#314 screen — a browser holding this payload from
    // before the field existed loses the standing questions and keeps every
    // control that matters.
    asks: w.sketch?.asks ?? [],
  },
  messages: (w.messages ?? []).map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    createdAt: m.created_at,
  })),
});

const fromServerCheckIn = (c: ServerCheckIn): CheckIn => ({
  id: c.id,
  date: c.date,
  phase: c.phase ?? "",
  amDeclaration: c.am_declaration,
  dueHour: c.due_hour ?? null,
  declarationFit: c.declaration_fit ?? "UNJUDGED",
  declarationReaction: c.declaration_reaction ?? "",
  sharpened: c.sharpened ?? "",
  proofAsk: c.proof_ask ?? "",
  proofOffer: c.proof_offer ?? "",
  proofMissing: c.proof_missing ?? "",
  // ?? rather than ||, for the reason metricValue below uses it: a drafted 0 is
  // a reading of zero, and the falsy check would turn it into "he heard
  // nothing" on exactly the evening worth showing.
  metricOffer: c.metric_offer ?? null,
  pmProofText: c.pm_proof_text,
  proofUrl: c.proof_url,
  proofImageUrl: c.proof_image_url ?? "",
  proofStatus: c.proof_status,
  coachReaction: c.coach_reaction,
  // `?? null` rather than `|| null`: 0 is a real reading, and the evening the
  // number did not move is the one worth looking at.
  metricValue: c.metric_value ?? null,
  metricLabel: c.metric_label ?? "",
  attempts: (c.attempts ?? []).map((a) => ({
    id: a.id,
    text: a.text,
    url: a.url,
    imageUrl: a.image_url,
    reaction: a.reaction,
    createdAt: a.created_at,
  })),
});

const fromServerGate = (g: ServerGate | null): Gate | null =>
  g && {
    have: g.have,
    need: g.need,
    nextPhase: g.next_phase,
    // Defaulted, not required: a client that outlives a rollback reads a
    // payload without it, and `owed` missing has to mean nothing is owed
    // rather than crashing the meter.
    owed: g.owed ?? [],
    // Same rule, and the default has to be `have`: absent means there is no
    // difference to explain, never a difference of `have` itself.
    banked: g.banked ?? g.have,
  };

const fromServerGoal = (g: ServerGoal): Goal => ({
  id: g.id,
  title: g.title,
  phase: g.phase,
  status: g.status,
  createdAt: g.created_at,
  titleLocked: g.title_locked ?? true,
  // Flattened at the boundary: the server's shape carries provenance the screen
  // has no use for (which parts the gate saw, who wrote it, when), and every
  // reader here wants the words.
  brief: g.brief?.text ?? "",
  considered: g.considered ?? [],
});

const fromServerRetirement = (r: ServerRetirement): Retirement => ({
  id: r.id,
  goalId: r.goal,
  title: r.title,
  outcome: r.outcome,
  readsAs: r.reads_as,
  reason: r.reason,
  phaseReached: r.phase_reached,
  acceptedProofs: r.accepted_proofs,
  contactProofs: r.contact_proofs,
  daysActive: r.days_active,
  bestStreak: r.best_streak,
  coachReaction: r.coach_reaction,
  createdAt: r.created_at,
  shareSlug: r.share_slug ?? null,
});

const fromServerTransition = (t: ServerTransition): PhaseTransition => ({
  fromPhase: t.from_phase,
  toPhase: t.to_phase,
  intent: t.intent ?? "",
  createdAt: t.created_at,
});

const fromServerMessage = (m: ServerMessage): ChatMessage => ({
  id: m.id,
  role: m.role,
  kind: m.kind ?? "NOTICE",
  content: m.content,
  phase: m.phase ?? "",
  createdAt: m.created_at,
});

/** When a phase was occupied, for the drill-in's date label: from the
 * transition that entered it (or the goal's creation, for the first phase)
 * to the transition that left it (null while it's the current phase).
 * Both ends are server timestamps, so rendering them through the browser's
 * locale converts to the reader's own clock correctly.
 *
 * This is LABEL ONLY — which check-ins belong to a phase comes from each
 * check-in's own stamped `phase`, never from comparing these timestamps to
 * CheckIn.date (which is a client-local date, a different clock). */
export function phaseWindow(
  phase: Phase,
  goal: Goal,
  transitions: PhaseTransition[]
): { start: string; end: string | null } {
  const into = transitions.find((t) => t.toPhase === phase);
  const outOf = transitions.find((t) => t.fromPhase === phase);
  return { start: into?.createdAt ?? goal.createdAt, end: outOf?.createdAt ?? null };
}

/** A check-in's day, written the way the reader writes days.
 *
 * `CheckIn.date` is a calendar date the client stamped — "2026-08-10", no
 * clock attached — and the record used to put it on screen three different
 * wrong ways: `date.slice(5)` gave "08-10" in the sidebar, and the day
 * drill-in and the closed-idea record printed the raw ISO string. "08-10" is
 * the worst of the three: this product is written for India, `en-IN` reads
 * day-first, and 10 August spent its whole life on screen claiming to be 8
 * October. The one place that already got this right is the changelog, and
 * this is its rule.
 *
 * Parsed AND formatted as UTC, for the reason Changelog.formatDate gives: a
 * bare "YYYY-MM-DD" parses as UTC midnight, so any reader west of Greenwich
 * renders it a day early. That is the opposite of `formatDate` in
 * Masterji.tsx, which takes phase-transition *timestamps* and must stay on the
 * reader's own clock — same-looking helpers, different clocks, which is why
 * they are named apart rather than merged.
 */
const day = (ymd: string, opts: Intl.DateTimeFormatOptions) =>
  new Date(`${ymd}T00:00:00Z`).toLocaleDateString("en-IN", {
    ...opts,
    timeZone: "UTC",
  });

/** "10 Aug" — the compact row in the record, where the goal supplies the year
 * and the column is narrow. */
export const formatDayShort = (ymd: string) =>
  day(ymd, { day: "numeric", month: "short" });

/** "10 Aug 2026" — the heading of a standalone day, which can be read months
 * later out of an archived idea and has room to say which year. */
export const formatDay = (ymd: string) =>
  day(ymd, { day: "numeric", month: "short", year: "numeric" });

/* --- plumbing ------------------------------------------------------------ */

async function refreshSession(): Promise<boolean> {
  const res = await fetch(`${API_URL}/api/auth/refresh/`, {
    method: "POST",
    credentials: "include",
  }).catch(() => null);
  return res?.ok ?? false;
}

/** The request itself: the timeout, the 401→refresh→replay, and a DRF refusal
 * turned into an ApiError. Hands back the raw Response because its two callers
 * read the body differently — everything here is JSON except the record export,
 * which is a file. Splitting at the body rather than writing a second wrapper
 * keeps the session refresh in one place, which is the part worth not copying.
 */
async function send(
  path: string,
  init: RequestInit = {},
  retried = false,
  timeoutMs = TIMEOUT_MS
): Promise<Response> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/coach/${path}`, {
      credentials: "include",
      signal: ctrl.signal,
      ...init,
      headers: {
        // FormData sets its own Content-Type: the multipart boundary is
        // generated per body, and a hardcoded header makes it unparseable.
        ...(init.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...init.headers,
      },
    });
  } catch {
    throw new Error("Couldn't reach Masterji — check your connection.");
  } finally {
    clearTimeout(t);
  }
  if (res.status === 401) {
    if (!retried && (await refreshSession()))
      return send(path, init, true, timeoutMs);
    throw new ApiError("Your session expired — sign in again.", 401);
  }
  if (!res.ok) throw new ApiError(await refusalFrom(res), res.status);
  return res;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  retried = false,
  timeoutMs = TIMEOUT_MS
): Promise<T> {
  const res = await send(path, init, retried, timeoutMs);
  return res.status === 204 ? (undefined as T) : res.json();
}

/* --- endpoints ------------------------------------------------------------ */

/** The browser's own date, YYYY-MM-DD. The server runs in UTC and a builder
 * does not, so which day the daily loop is on is the browser's to say. Sent
 * on every call that writes to a day OR reads one — a read that skipped it
 * looked for today's task under yesterday's date and found nothing.
 *
 * Exported because the morning's draft is filed under a day too, and the day
 * it is filed under has to be the same one this module asks the server about.
 * A second copy of this arithmetic in the component is the bug in the comment
 * above, waiting to happen twice. */
export const localDate = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
};

export async function getState(): Promise<CoachState> {
  const data = await request<{
    goal: ServerGoal | null;
    gate?: ServerGate;
    streak?: number;
    best_streak?: number;
    days_in_phase?: number;
    today?: ServerCheckIn | null;
    checkins?: ServerCheckIn[];
    checkins_total?: number;
    transitions?: ServerTransition[];
    messages?: ServerMessage[];
    phases?: Phase[];
    guidance?: {
      phase_hint: string;
      proof_hint: string;
      proof_examples: string[];
      openers?: string[];
    };
    uploads_enabled?: boolean;
    at_finish_line?: boolean;
    archive?: ServerRetirement[];
    lifetime_days?: number;
    tone: CoachState["tone"];
    mode?: CoachState["mode"];
    launch?: {
      date: string;
      pond: string;
      pond_label: string;
      days_out: number;
      moves: number;
      first: string;
    } | null;
    can_set_launch?: boolean;
    ponds?: { value: string; label: string }[];
    metric?: ServerMetric | null;
    can_set_metric?: boolean;
    declaration_offer?: string;
    workshop?: ServerWorkshop | null;
    workshop_openers?: string[];
    workshop_turns?: number;
  }>(`state/?date=${localDate()}`);
  return {
    goal: data.goal ? fromServerGoal(data.goal) : null,
    gate: fromServerGate(data.gate ?? null),
    guidance: data.guidance
      ? {
          phaseHint: data.guidance.phase_hint,
          proofHint: data.guidance.proof_hint,
          proofExamples: data.guidance.proof_examples,
          // Defaulted rather than required: a browser holding this bundle can
          // outlive the deploy that starts sending it, and an empty list is
          // already the "don't offer any" case the chat pane handles.
          openers: data.guidance.openers ?? [],
        }
      : null,
    streak: data.streak ?? 0,
    bestStreak: data.best_streak ?? 0,
    // Defaulted like the rest: a browser holding this bundle can outlive the
    // deploy that starts sending the field, and 0 is already the case the
    // header renders nothing for.
    daysInPhase: data.days_in_phase ?? 0,
    today: data.today ? fromServerCheckIn(data.today) : null,
    // Defaulted like the rest, and "" is already the case the card draws
    // nothing for — a browser holding this bundle from before the field
    // existed sees the morning exactly as it was.
    declarationOffer: data.declaration_offer ?? "",
    checkins: (data.checkins ?? []).map(fromServerCheckIn),
    // Falls back to what arrived, so a browser holding this bundle from before
    // the field existed reads "nothing is missing" rather than "everything is".
    checkinsTotal: data.checkins_total ?? (data.checkins ?? []).length,
    transitions: (data.transitions ?? []).map(fromServerTransition),
    messages: (data.messages ?? []).map(fromServerMessage),
    phases: data.phases ?? [
      "IDEA",
      "VALIDATION",
      "BUILD",
      "LAUNCH",
      "TRACTION",
    ],
    uploadsEnabled: data.uploads_enabled ?? false,
    atFinishLine: data.at_finish_line ?? false,
    archive: (data.archive ?? []).map(fromServerRetirement),
    lifetimeDays: data.lifetime_days ?? 0,
    tone: data.tone,
    mode: data.mode ?? "COACH",
    workshop: data.workshop ? fromServerWorkshop(data.workshop) : null,
    workshopOpeners: data.workshop_openers ?? [],
    workshopTurns: data.workshop_turns ?? 0,
    launch: data.launch
      ? {
          date: data.launch.date,
          pond: data.launch.pond,
          pondLabel: data.launch.pond_label,
          daysOut: data.launch.days_out,
          moves: data.launch.moves,
          first: data.launch.first,
        }
      : null,
    canSetLaunch: data.can_set_launch ?? false,
    ponds: data.ponds ?? [],
    metric: fromServerMetric(data.metric ?? null),
    canSetMetric: data.can_set_metric ?? false,
  };
}

export type GoalHistory = {
  goal: Goal;
  retirement: Retirement | null;
  checkins: CheckIn[];
  transitions: PhaseTransition[];
  bestStreak: number;
};

/** The full day-by-day record of one goal, closed or current. Fetched lazily —
 * it's a lot of rows for a panel that's usually shut. */
export async function getGoalHistory(id: number): Promise<GoalHistory> {
  const data = await request<{
    goal: ServerGoal;
    retirement: ServerRetirement | null;
    checkins: ServerCheckIn[];
    transitions: ServerTransition[];
    streak: number;
  }>(`goals/${id}/history/`);
  return {
    goal: fromServerGoal(data.goal),
    retirement: data.retirement ? fromServerRetirement(data.retirement) : null,
    checkins: data.checkins.map(fromServerCheckIn),
    transitions: data.transitions.map(fromServerTransition),
    bestStreak: data.streak,
  };
}

export const EXPORT_MIME = "text/markdown";

/** The whole record of one goal as a file the builder keeps — every day's
 * declaration, proof and verdict, the tries that were pushed back, the phases
 * as they opened, and how it ended.
 *
 * Rendered by the server, named by the server. This fetches it rather than
 * linking to the endpoint so an expired session is refreshed and replayed the
 * way it is everywhere else; a plain navigation would download the error page.
 */
export async function exportGoal(
  id: number
): Promise<{ filename: string; text: string }> {
  const res = await send(`goals/${id}/export/`);
  return {
    filename: filenameFrom(
      res.headers.get("Content-Disposition"),
      "masterji-record.md"
    ),
    text: await res.text(),
  };
}

/** One line of the product's own record. Written in the admin, not in the
 * client — the list is the same for every reader, so nothing here is scoped
 * to a user. */
export type ChangelogEntry = {
  id: number;
  /** YYYY-MM-DD — the day the change reached builders. */
  shippedOn: string;
  kind: "NEW" | "CHANGED" | "FIXED" | "METHOD";
  title: string;
  body: string;
};

/** Active entries, newest first, and how many there are in all. The one
 * endpoint here that answers without a session, so the demo and the signed-out
 * screens can read it.
 *
 * `limit` asks for the newest N instead of the lot. Every screen mounts the
 * changelog to decide whether to show one dot, and the full list had reached
 * 42KB — so the mount asks for a preview and the popup asks for the rest.
 * `total` is what tells the caller which of those two it is holding. */
export async function getChangelog(
  limit?: number
): Promise<{ entries: ChangelogEntry[]; total: number }> {
  const data = await request<{
    entries: {
      id: number;
      shipped_on: string;
      kind: ChangelogEntry["kind"];
      title: string;
      body: string;
    }[];
    total?: number;
  }>(`changelog/${limit ? `?limit=${limit}` : ""}`);
  const entries = (data.entries ?? []).map((e) => ({
    id: e.id,
    shippedOn: e.shipped_on,
    kind: e.kind,
    title: e.title,
    body: e.body,
  }));
  // `total` absent means a server that predates it, which can only be serving
  // the whole list — so what arrived IS all of them.
  return { entries, total: data.total ?? entries.length };
}

/** Retire the active goal. Always permitted — a reason is required, and the
 * server derives whether the idea was actually tested. */
export async function retireGoal(
  id: number,
  reason: string,
  outcome: "ABANDONED" | "COMPLETED" = "ABANDONED"
): Promise<{ retirement: Retirement; readsAs: Retirement["readsAs"] }> {
  const path = outcome === "COMPLETED" ? "complete" : "retire";
  const data = await request<{
    retirement: ServerRetirement;
    reads_as: Retirement["readsAs"];
  }>(`goals/${id}/${path}/`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
  return {
    retirement: fromServerRetirement(data.retirement),
    readsAs: data.reads_as,
  };
}

/** `pivotedFrom` is the closed goal this one came out of — "same problem, new
 * idea". A link and nothing else: the successor starts at IDEA with zero
 * proofs and the gate is never seeded. The server drops the link if it is not
 * the builder's own closed goal, rather than refusing the commit: the goal is
 * what they are committing to and the link is a footnote. */
export async function createGoal(
  title: string,
  pivotedFrom?: number | null
): Promise<Goal> {
  const data = await request<ServerGoal>("goals/", {
    method: "POST",
    body: JSON.stringify(
      pivotedFrom ? { title, pivoted_from: pivotedFrom } : { title }
    ),
  });
  return fromServerGoal(data);
}

/** Sharpen the wording of a goal nothing has been banked against yet. 409 =
 * the record already points at it (comes back as ApiError, and its message is
 * the whole of what the builder needs to read). */
export async function updateGoalTitle(id: number, title: string): Promise<Goal> {
  const data = await request<ServerGoal>(`goals/${id}/`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
  return fromServerGoal(data);
}

/** The deterministic gate. 409 = refused (comes back as ApiError). */
export async function advanceGoal(
  id: number
): Promise<{ advanced: boolean; phase: Phase; detail: string }> {
  return request(`goals/${id}/advance/`, { method: "POST" });
}

/** One line on what the phase you just unlocked will produce. Never a gate:
 * skipping it advances the phase exactly as before, and the server refuses only
 * an empty line, a paragraph, or a phase nothing unlocked (IDEA → 409). */
export async function setPhaseIntent(
  id: number,
  intent: string
): Promise<PhaseTransition> {
  const data = await request<ServerTransition>(`goals/${id}/intent/`, {
    method: "POST",
    body: JSON.stringify({ intent }),
  });
  return fromServerTransition(data);
}

/** Name the day you'll launch, and the room you'll launch into. Append-only:
 * this never edits the last answer, it writes another row, so the record keeps
 * the trail. `today` is sent separately from `date` because the body carries
 * two of them and only one is the builder's clock. */
export async function setLaunchDate(
  id: number,
  when: string,
  pond: string
): Promise<LaunchDate> {
  const data = await request<{
    date: string;
    pond: string;
    pond_label: string;
    days_out: number;
    moves: number;
    first: string;
  }>(`goals/${id}/launch/`, {
    method: "POST",
    body: JSON.stringify({ date: when, pond, today: localDate() }),
  });
  return {
    date: data.date,
    pond: data.pond,
    pondLabel: data.pond_label,
    daysOut: data.days_out,
    moves: data.moves,
    first: data.first,
  };
}

/** Name the one number you're watching. TRACTION only — anywhere else is a 409,
 * and its message is the whole of what the builder needs to read.
 *
 * Re-settable, and no gate reads it: a metric that falls, stays flat or gets
 * renamed refuses nothing. The slip that renaming leaves is on the readings
 * themselves (`CheckIn.metricLabel`), not here. */
export async function setMetric(id: number, name: string): Promise<Metric> {
  const data = await request<ServerMetric>(`goals/${id}/metric/`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  // Never null: the endpoint 400s an empty name, so a 200 means one is set.
  return fromServerMetric(data)!;
}

/** Read a shared record by its slug. No auth: this is the one endpoint in the
 * app a signed-out stranger is meant to reach. A missing, revoked or wrong
 * slug is the same 404 in every case — the difference between "no such record"
 * and "that one is private" is itself something a stranger could walk. */
export async function getSharedRecord(slug: string): Promise<SharedRecord> {
  const data = await request<{
    title: string;
    outcome: "ABANDONED" | "COMPLETED";
    reads_as: SharedRecord["readsAs"];
    phase_reached: Phase;
    accepted_proofs: number;
    contact_proofs: number;
    days_active: number;
    best_streak: number;
    started_on: string;
    closed_on: string;
    timeline: { to_phase: Phase; on: string }[];
  }>(`record/${encodeURIComponent(slug)}/`);
  return {
    title: data.title,
    outcome: data.outcome,
    readsAs: data.reads_as,
    phaseReached: data.phase_reached,
    acceptedProofs: data.accepted_proofs,
    contactProofs: data.contact_proofs,
    daysActive: data.days_active,
    bestStreak: data.best_streak,
    startedOn: data.started_on,
    closedOn: data.closed_on,
    timeline: data.timeline.map((t) => ({ toPhase: t.to_phase, on: t.on })),
  };
}

/** Turn the public link on or off. Turning it on after revoking mints a
 * DIFFERENT slug: a link handed out and regretted has to be able to stop
 * working, and a switch that resurrects the old URL only ever paused it.
 *
 * Two verbs rather than one call carrying a boolean. That was the first shape
 * and a form-encoded `false` came back as the string "False", which is truthy
 * — the switch turned the link ON when asked to take it away. */
export async function shareRecord(
  retirementId: number,
  on: boolean
): Promise<string | null> {
  const data = await request<{ share_slug: string | null }>(
    `retirements/${retirementId}/share/`,
    { method: on ? "POST" : "DELETE" }
  );
  return data.share_slug;
}

/* --- cohorts -------------------------------------------------------------- */

/** A cohort you have joined. There is no way to list cohorts you have not:
 * joining by code is the consent, and a directory would make the code
 * pointless. */
export type Cohort = {
  id: number;
  name: string;
  /** Live memberships. People who left are not in it. */
  members: number;
};

/** One builder's line on a cohort board — counts, and nothing they typed.
 *
 * No goal title, no brief, no proof text, no email. Every number here was
 * computed by the server from evidence that cleared a gate, which is the whole
 * difference between this and a leaderboard of self-reports. */
export type CohortRow = {
  /** Their first name, or the username it falls back to. */
  name: string;
  /** Shared by ties, and null for a member with no active goal — they have
   * nothing on the board to be ranked on, and ranking an absence is the board
   * making a judgement the record does not contain. */
  rank: number | null;
  hasGoal: boolean;
  phase: Phase | null;
  /** Where that phase sits on the ladder, so the client never has to know the
   * order of the strings. -1 when there is no goal. */
  phaseIndex: number;
  acceptedProofs: number;
  /** The VALIDATION-onward subset: the ones that needed a real person. This is
   * the column the board is sorted on. */
  contactProofs: number;
  streak: number;
};

export type CohortBoard = { cohort: Cohort; board: CohortRow[] };

type ServerCohort = { id: number; name: string; members: number };
type ServerCohortRow = {
  name: string;
  rank: number | null;
  has_goal: boolean;
  phase: Phase | null;
  phase_index: number;
  accepted_proofs: number;
  contact_proofs: number;
  streak: number;
};

const fromServerCohort = (c: ServerCohort): Cohort => ({
  id: c.id,
  name: c.name,
  members: c.members,
});

const fromServerCohortRow = (r: ServerCohortRow): CohortRow => ({
  name: r.name,
  rank: r.rank,
  hasGoal: r.has_goal,
  phase: r.phase,
  phaseIndex: r.phase_index,
  acceptedProofs: r.accepted_proofs,
  contactProofs: r.contact_proofs,
  streak: r.streak,
});

/** The cohorts this builder has joined. Empty is the normal state. */
export async function getCohorts(): Promise<Cohort[]> {
  const data = await request<{ cohorts: ServerCohort[] }>("cohorts/");
  return (data.cohorts ?? []).map(fromServerCohort);
}

/** One cohort's board. 404 for a cohort you are not in — identical to one that
 * does not exist, deliberately, so the endpoint cannot be walked to find out
 * which cohorts there are. */
export async function getCohortBoard(id: number): Promise<CohortBoard> {
  const data = await request<{ cohort: ServerCohort; board: ServerCohortRow[] }>(
    `cohorts/${id}/`
  );
  return {
    cohort: fromServerCohort(data.cohort),
    board: (data.board ?? []).map(fromServerCohortRow),
  };
}

/** Join by code — the act that agrees to be counted where your cohort can see
 * it. Idempotent: joining one you are already in returns the same membership.
 * A wrong code is an ApiError with the server's own sentence in it. */
export async function joinCohort(code: string): Promise<Cohort> {
  const data = await request<{ cohort: ServerCohort }>("cohorts/join/", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
  return fromServerCohort(data.cohort);
}

/** Leave. Removes the membership row and nothing else — every goal, check-in
 * and proof is untouched, so the record is identical the day after. */
export async function leaveCohort(id: number): Promise<void> {
  await request<void>(`cohorts/${id}/membership/`, { method: "DELETE" });
}

/** `dueHour` is the hour the builder says tonight's proof will land, and it is
 * always sent — null when they named none, which is how an hour gets taken
 * back. The declaration is one statement including its hour, so the server
 * writes the whole of it rather than patching a field at a time.
 *
 * `metricValue` is today's reading of the one number, for a morning the builder
 * already has it. Unlike the hour it is omitted rather than sent as null, and
 * that difference is the two fields' contracts: an absent hour MEANS cleared,
 * while an absent reading means nothing was read — the server never wipes a
 * number the day already holds. Ignored outside TRACTION or before a metric is
 * named, because a number may not cost somebody their declaration, so check the
 * returned row rather than assuming it landed. */
export async function declare(
  text: string,
  dueHour: number | null = null,
  metricValue?: number | null
): Promise<CheckIn> {
  const data = await request<ServerCheckIn>("checkins/declare/", {
    method: "POST",
    body: JSON.stringify({
      text,
      date: localDate(),
      due_hour: dueHour,
      ...(metricValue == null ? {} : { metric_value: metricValue }),
    }),
  });
  return fromServerCheckIn(data);
}

/** Ask Masterji to read a declaration already on the record. Deliberately a
 * second call: `declare` returns before any model runs, so the task appears
 * the instant it's typed. Fire this after and refresh when it lands — if it
 * never does, the check-in stays UNJUDGED, which is a valid state. */
export async function judgeDeclaration(id: number): Promise<CheckIn> {
  const data = await request<ServerCheckIn>(`checkins/${id}/judge/`, {
    method: "POST",
  });
  return fromServerCheckIn(data);
}

/** Uploading and grading a screenshot is slower than a text proof — the
 * bytes go up, then a vision model reads them, possibly on a cold dyno. */
const PROVE_WITH_IMAGE_TIMEOUT_MS = 60000;

/** `metricValue` is the evening's reading of the one number — the end of the day
 * the builder actually knows it. Same contract as `declare`: optional, dropped
 * rather than refused when it cannot be recorded, so it never costs the proof. */
export async function prove(
  text: string,
  url: string,
  image?: File | null,
  metricValue?: number | null
): Promise<{ checkin: CheckIn; gate: Gate | null; streak: number }> {
  let body: BodyInit;
  if (image) {
    const form = new FormData();
    form.set("text", text);
    form.set("url", url);
    form.set("date", localDate());
    form.set("image", image);
    // Only when there is one. An empty string here would reach the server as a
    // value that is present and unparseable rather than as absent.
    if (metricValue != null) form.set("metric_value", String(metricValue));
    body = form;
  } else {
    body = JSON.stringify({
      text,
      url,
      date: localDate(),
      ...(metricValue == null ? {} : { metric_value: metricValue }),
    });
  }
  const data = await request<{
    checkin: ServerCheckIn;
    gate: ServerGate;
    streak: number;
  }>(
    "checkins/prove/",
    { method: "POST", body },
    false,
    image ? PROVE_WITH_IMAGE_TIMEOUT_MS : TIMEOUT_MS
  );
  return {
    checkin: fromServerCheckIn(data.checkin),
    gate: fromServerGate(data.gate),
    streak: data.streak,
  };
}

/* --- streaming chat -------------------------------------------------------- */

export type ChatEvents = {
  onDelta: (text: string) => void;
  onGate: (gate: { advanced: boolean; phase: Phase; detail: string }) => void;
  /** Masterji proposed closing the goal — open the retire box on the card.
   *
   * Carries no payload because nothing happened on the server: unlike the gate
   * above, which arrives with an answer the server computed, this one is a
   * request to move the UI and the goal is still active behind it. Closing is
   * `retireGoal`, from a reason and an exit the builder supplies themselves. */
  onCloseProposed: () => void;
  onError: (detail: string) => void;
};

export type WorkshopEvents = {
  onDelta: (text: string) => void;
  /** A candidate was parked, a title was suggested, or a fourth park was
   * refused. `refused` is surfaced rather than swallowed: the builder is
   * watching a suggestion not appear, and silence there reads as the app
   * dropping their idea. */
  onCandidates: (c: {
    candidates: string[];
    suggested: string;
    refused: boolean;
  }) => void;
  onError: (detail: string) => void;
};

/** One event off either wire, exactly as `JSON.parse` hands it over: `t` says
 * which kind it is, and the payload is whatever that kind carries.
 *
 * `any` on purpose, and named here rather than left implicit the way the two
 * hand-rolled readers left it. The checked boundary is one line further in —
 * each dispatcher below tests `t` and then reads only the fields that kind has,
 * against the `ChatEvents`/`WorkshopEvents` signatures. A union written out
 * here would be a second declaration of the wire format, kept in step with
 * `views.py` by hand, which is the shape of duplication this change exists to
 * remove rather than add. */
type WireEvent = any;

/** POST a turn and consume its NDJSON stream, handing each event to the
 * dispatcher for that wire. Resolves when the server closes the stream.
 *
 * The two turns share everything except which events they understand: the same
 * body, the same 401→refresh→replay, the same refusal surfacing, the same
 * reader. `dispatch` is a parameter rather than a flag because the vocabularies
 * genuinely differ — a coaching turn can propose a phase advance or a close, a
 * workshop turn can park a candidate — and a single function that switched on a
 * mode would be pretending those are one thing.
 *
 * Deliberately NOT routed through `send()`, despite sharing most of its job,
 * and the reason is worth stating so nobody has to re-derive it: `send` wraps a
 * network failure in its own sentence, and both callers below report
 * `e.message` straight to the builder, so folding these in would rewrite what a
 * dropped connection says mid-turn — a behaviour change inside a refactor that
 * promised none. Its abort timeout is *not* the obstacle, for the record: it is
 * cleared the moment the headers land, which is before the first chunk of a
 * stream is read. Worth doing on purpose one day, in a change that says so.
 */
async function streamTurn(
  path: string,
  content: string,
  dispatch: (event: WireEvent) => void,
  retried = false
): Promise<void> {
  const res = await fetch(`${API_URL}/api/coach/${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    // The date goes with it, and both rooms have their own reason to want it.
    // The coaching turn needs Masterji told about the task on the hook today —
    // without it he opens a 1am conversation insisting nothing has been
    // declared, while it's on screen next to him. The reopened workshop needs
    // it to count "day 4 of BUILD", which is off by one for every builder
    // ahead of UTC otherwise. The pre-goal room ignores it.
    body: JSON.stringify({ content, date: localDate() }),
  });
  if (res.status === 401) {
    if (!retried && (await refreshSession()))
      return streamTurn(path, content, dispatch, true);
    throw new ApiError("Your session expired — sign in again.", 401);
  }
  // Both caps land here — chat's hourly throttle and the workshop's turn budget
  // — and both refusals are a sentence Masterji wrote. Read it out rather than
  // replacing it with "Masterji said no (429)".
  if (!res.ok || !res.body) throw new ApiError(await refusalFrom(res), res.status);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const feed = ndjsonFeed<WireEvent>();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const event of feed(decoder.decode(value, { stream: true })))
      dispatch(event);
  }
}

/** POST the message and consume the NDJSON stream. Resolves when done. */
export async function streamChat(
  content: string,
  events: ChatEvents
): Promise<void> {
  return streamTurn("chat/", content, (event) => {
    if (event.t === "delta") events.onDelta(event.text);
    else if (event.t === "gate") events.onGate(event);
    else if (event.t === "close") events.onCloseProposed();
    else if (event.t === "error") events.onError(event.detail);
  });
}

/** POST a workshop turn and consume the NDJSON stream. Resolves when done.
 *
 * Deliberately a sibling of streamChat rather than a flag on it: the events the
 * two carry are different, and the rooms are no longer even mutually exclusive
 * — the workshop learned to reopen behind a live goal, so a builder can be in
 * both. What they do share is `streamTurn` above.
 *
 * A 429 here is the turn cap, and its detail line is the coach's own words —
 * surfaced as an ApiError so the pane can show it where the reply would have
 * gone. */
export async function streamWorkshopChat(
  content: string,
  events: WorkshopEvents
): Promise<void> {
  return streamTurn("workshop/chat/", content, (event) => {
    if (event.t === "delta") events.onDelta(event.text);
    else if (event.t === "candidates") events.onCandidates(event);
    else if (event.t === "error") events.onError(event.detail);
  });
}

/* --- the evening nudge (#87) --------------------------------------------- */

/** What this deployment can do about push, asked before anything is offered.
 *
 * `configured` is false on every checkout with no VAPID keys set, which is
 * all of them until DEPLOY.md §8 is done — and the control draws nothing at
 * all in that case rather than offering a switch that would 503. */
export type PushConfig = {
  configured: boolean;
  publicKey: string;
  /** The hour the server considers a builder's evening to have started. Sent
   * so the control can say WHEN the nudge would arrive without a second copy
   * of the number living over here — app/Masterji.tsx already keeps one for
   * the Today card and two would be one too many. */
  eveningFrom: number;
};

export async function getPushConfig(): Promise<PushConfig> {
  const data = await request<{
    configured: boolean;
    public_key: string;
    evening_from: number;
  }>("push/");
  return {
    configured: data.configured,
    publicKey: data.public_key,
    eveningFrom: data.evening_from,
  };
}

/** Hand the server this browser's subscription. Sent verbatim in the shape
 * `PushSubscription.toJSON()` produces, plus the zone — the server stores the
 * three strings and nothing else, because the three strings ARE the
 * permission to push to this device. */
export async function savePushSubscription(subscription: {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  timezone: string;
}): Promise<void> {
  await request("push/", {
    method: "POST",
    body: JSON.stringify(subscription),
  });
}

/** Drop it. No endpoint means every device on this account, which is the
 * honest reading of an off switch pressed by somebody who cannot see a
 * device list — and the only reading available when the browser has already
 * lost the subscription it would otherwise name. */
export async function dropPushSubscription(endpoint?: string): Promise<void> {
  await request("push/", {
    method: "DELETE",
    body: JSON.stringify(endpoint ? { endpoint } : {}),
  });
}
