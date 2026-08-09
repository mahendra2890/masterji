"use client";

// Coach API client (journal-api pattern from the portfolio): one request()
// with a timeout, a 401→refresh→replay retry, DRF error surfacing, and
// snake_case → camelCase mappers at the boundary. Chat is the exception —
// it streams NDJSON and gets its own reader below.

import { API_URL } from "@/lib/auth-client";

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

export type Phase = "IDEA" | "VALIDATION" | "BUILD" | "LAUNCH";

export type Goal = {
  id: number;
  title: string;
  phase: Phase;
  status: string;
  createdAt: string;
};

export type Gate = { have: number; need: number; nextPhase: Phase | null };

export type PhaseTransition = {
  fromPhase: Phase;
  toPhase: Phase;
  createdAt: string;
};

/** A proof submission Masterji pushed back, kept when the builder answered
 * it with a new one. The check-in's own fields are always the CURRENT
 * proof; these are the tries before it, oldest first. */
export type ProofAttempt = {
  id: number;
  text: string;
  url: string;
  /** Signed, short-lived; "" when the try had no image. */
  imageUrl: string;
  reaction: string;
  createdAt: string;
};

export type CheckIn = {
  id: number;
  date: string; // YYYY-MM-DD, from the CLIENT's local clock
  phase: Phase | ""; // stamped server-side; "" only for pre-migration rows
  amDeclaration: string;
  /** Whether this morning's task is the work the phase is for. Advisory —
   * an off-phase task is still allowed and still earns its proof.
   * UNJUDGED means the model was unreachable, not that it passed. */
  declarationFit: "UNJUDGED" | "ON_PHASE" | "OFF_PHASE";
  declarationReaction: string;
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
  pmProofText: string;
  proofUrl: string;
  /** Signed, short-lived link to the screenshot backing this proof. Minted
   * per read and expires in minutes — never persist or share it. "" when
   * there's no image or storage isn't configured. */
  proofImageUrl: string;
  proofStatus: "NONE" | "ACCEPTED" | "PUSHED_BACK";
  coachReaction: string;
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
  content: string;
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
  today: CheckIn | null;
  checkins: CheckIn[];
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
};

/* --- server shapes ------------------------------------------------------ */

type ServerGoal = {
  id: number;
  title: string;
  phase: Phase;
  status: string;
  created_at: string;
};
type ServerGate = { have: number; need: number; next_phase: Phase | null };
type ServerTransition = {
  from_phase: Phase;
  to_phase: Phase;
  created_at: string;
};
type ServerRetirement = {
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
  declaration_fit?: CheckIn["declarationFit"];
  declaration_reaction?: string;
  proof_ask?: string;
  proof_offer?: string;
  proof_missing?: string;
  pm_proof_text: string;
  proof_url: string;
  proof_image_url?: string;
  proof_status: CheckIn["proofStatus"];
  coach_reaction: string;
  attempts?: {
    id: number;
    text: string;
    url: string;
    image_url: string;
    reaction: string;
    created_at: string;
  }[];
};
type ServerMessage = {
  id: number;
  role: "USER" | "COACH" | "SYSTEM";
  content: string;
  created_at: string;
};

const fromServerCheckIn = (c: ServerCheckIn): CheckIn => ({
  id: c.id,
  date: c.date,
  phase: c.phase ?? "",
  amDeclaration: c.am_declaration,
  declarationFit: c.declaration_fit ?? "UNJUDGED",
  declarationReaction: c.declaration_reaction ?? "",
  proofAsk: c.proof_ask ?? "",
  proofOffer: c.proof_offer ?? "",
  proofMissing: c.proof_missing ?? "",
  pmProofText: c.pm_proof_text,
  proofUrl: c.proof_url,
  proofImageUrl: c.proof_image_url ?? "",
  proofStatus: c.proof_status,
  coachReaction: c.coach_reaction,
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
  g && { have: g.have, need: g.need, nextPhase: g.next_phase };

const fromServerGoal = (g: ServerGoal): Goal => ({
  id: g.id,
  title: g.title,
  phase: g.phase,
  status: g.status,
  createdAt: g.created_at,
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
});

const fromServerTransition = (t: ServerTransition): PhaseTransition => ({
  fromPhase: t.from_phase,
  toPhase: t.to_phase,
  createdAt: t.created_at,
});

const fromServerMessage = (m: ServerMessage): ChatMessage => ({
  id: m.id,
  role: m.role,
  content: m.content,
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

async function request<T>(
  path: string,
  init: RequestInit = {},
  retried = false,
  timeoutMs = TIMEOUT_MS
): Promise<T> {
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
      return request<T>(path, init, true, timeoutMs);
    throw new ApiError("Your session expired — sign in again.", 401);
  }
  if (!res.ok) {
    let msg = `Masterji said no (${res.status}).`;
    try {
      const body = (await res.json()) as Record<string, unknown>;
      // DRF sends {"detail": ...} or field errors; the gate sends its
      // refusal in "detail" alongside non-string fields.
      const first =
        typeof body.detail === "string"
          ? body.detail
          : Object.values(body)
              .flat()
              .find((v) => typeof v === "string");
      if (typeof first === "string") msg = first;
    } catch {}
    throw new ApiError(msg, res.status);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

/* --- endpoints ------------------------------------------------------------ */

/** The browser's own date, YYYY-MM-DD. The server runs in UTC and a builder
 * does not, so which day the daily loop is on is the browser's to say. Sent
 * on every call that writes to a day OR reads one — a read that skipped it
 * looked for today's task under yesterday's date and found nothing. */
const localDate = () => {
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
    today?: ServerCheckIn | null;
    checkins?: ServerCheckIn[];
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
    today: data.today ? fromServerCheckIn(data.today) : null,
    checkins: (data.checkins ?? []).map(fromServerCheckIn),
    transitions: (data.transitions ?? []).map(fromServerTransition),
    messages: (data.messages ?? []).map(fromServerMessage),
    phases: data.phases ?? ["IDEA", "VALIDATION", "BUILD", "LAUNCH"],
    uploadsEnabled: data.uploads_enabled ?? false,
    atFinishLine: data.at_finish_line ?? false,
    archive: (data.archive ?? []).map(fromServerRetirement),
    lifetimeDays: data.lifetime_days ?? 0,
    tone: data.tone,
    mode: data.mode ?? "COACH",
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

/** Every active entry, newest first. The one endpoint here that answers
 * without a session, so the demo and the signed-out screens can read it. */
export async function getChangelog(): Promise<ChangelogEntry[]> {
  const data = await request<{
    entries: {
      id: number;
      shipped_on: string;
      kind: ChangelogEntry["kind"];
      title: string;
      body: string;
    }[];
  }>("changelog/");
  return (data.entries ?? []).map((e) => ({
    id: e.id,
    shippedOn: e.shipped_on,
    kind: e.kind,
    title: e.title,
    body: e.body,
  }));
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

export async function createGoal(title: string): Promise<Goal> {
  const data = await request<ServerGoal>("goals/", {
    method: "POST",
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

export async function declare(text: string): Promise<CheckIn> {
  const data = await request<ServerCheckIn>("checkins/declare/", {
    method: "POST",
    body: JSON.stringify({ text, date: localDate() }),
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

export async function prove(
  text: string,
  url: string,
  image?: File | null
): Promise<{ checkin: CheckIn; gate: Gate | null; streak: number }> {
  let body: BodyInit;
  if (image) {
    const form = new FormData();
    form.set("text", text);
    form.set("url", url);
    form.set("date", localDate());
    form.set("image", image);
    body = form;
  } else {
    body = JSON.stringify({ text, url, date: localDate() });
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
  onError: (detail: string) => void;
};

/** POST the message and consume the NDJSON stream. Resolves when done. */
export async function streamChat(
  content: string,
  events: ChatEvents,
  retried = false
): Promise<void> {
  const res = await fetch(`${API_URL}/api/coach/chat/`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    // The date goes with it so Masterji is told about the task on the hook
    // today — without it he opens a 1am conversation insisting nothing has
    // been declared, while it's on screen next to him.
    body: JSON.stringify({ content, date: localDate() }),
  });
  if (res.status === 401) {
    if (!retried && (await refreshSession())) return streamChat(content, events, true);
    throw new ApiError("Your session expired — sign in again.", 401);
  }
  if (!res.ok || !res.body) throw new ApiError(`Masterji said no (${res.status}).`, res.status);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const raw of lines) {
      if (!raw.trim()) continue;
      const event = JSON.parse(raw);
      if (event.t === "delta") events.onDelta(event.text);
      else if (event.t === "gate") events.onGate(event);
      else if (event.t === "error") events.onError(event.detail);
    }
  }
}
