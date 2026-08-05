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

export type CheckIn = {
  id: number;
  date: string; // YYYY-MM-DD, from the CLIENT's local clock
  phase: Phase | ""; // stamped server-side; "" only for pre-migration rows
  amDeclaration: string;
  pmProofText: string;
  proofUrl: string;
  proofStatus: "NONE" | "ACCEPTED" | "PUSHED_BACK";
  coachReaction: string;
};

export type ChatMessage = {
  id: number;
  role: "USER" | "COACH";
  content: string;
  createdAt: string;
};

export type Retirement = {
  id: number;
  title: string;
  outcome: "ABANDONED" | "COMPLETED";
  /** Derived server-side from earned proofs — never self-reported. */
  readsAs: "INVALIDATED" | "UNTESTED";
  reason: string;
  phaseReached: Phase;
  contactProofs: number;
  daysActive: number;
  bestStreak: number;
  coachReaction: string;
  createdAt: string;
};

export type CoachState = {
  goal: Goal | null;
  gate: Gate | null;
  streak: number;
  today: CheckIn | null;
  checkins: CheckIn[];
  transitions: PhaseTransition[];
  messages: ChatMessage[];
  phases: Phase[];
  canComplete: boolean;
  /** Retired goals, newest first — the record that outlives each idea. */
  archive: Retirement[];
  /** Days declared-and-proved across every goal, so retiring an idea doesn't
   * erase the fact that the work happened. */
  lifetimeDays: number;
  tone: "ENGLISH" | "HINGLISH";
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
  title: string;
  outcome: Retirement["outcome"];
  reads_as: Retirement["readsAs"];
  reason: string;
  phase_reached: Phase;
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
  pm_proof_text: string;
  proof_url: string;
  proof_status: CheckIn["proofStatus"];
  coach_reaction: string;
};
type ServerMessage = {
  id: number;
  role: "USER" | "COACH";
  content: string;
  created_at: string;
};

const fromServerCheckIn = (c: ServerCheckIn): CheckIn => ({
  id: c.id,
  date: c.date,
  phase: c.phase ?? "",
  amDeclaration: c.am_declaration,
  pmProofText: c.pm_proof_text,
  proofUrl: c.proof_url,
  proofStatus: c.proof_status,
  coachReaction: c.coach_reaction,
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
  title: r.title,
  outcome: r.outcome,
  readsAs: r.reads_as,
  reason: r.reason,
  phaseReached: r.phase_reached,
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
  retried = false
): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/coach/${path}`, {
      credentials: "include",
      signal: ctrl.signal,
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    throw new Error("Couldn't reach Masterji — check your connection.");
  } finally {
    clearTimeout(t);
  }
  if (res.status === 401) {
    if (!retried && (await refreshSession())) return request<T>(path, init, true);
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

export async function getState(): Promise<CoachState> {
  const data = await request<{
    goal: ServerGoal | null;
    gate?: ServerGate;
    streak?: number;
    today?: ServerCheckIn | null;
    checkins?: ServerCheckIn[];
    transitions?: ServerTransition[];
    messages?: ServerMessage[];
    phases?: Phase[];
    can_complete?: boolean;
    archive?: ServerRetirement[];
    lifetime_days?: number;
    tone: CoachState["tone"];
  }>("state/");
  return {
    goal: data.goal ? fromServerGoal(data.goal) : null,
    gate: fromServerGate(data.gate ?? null),
    streak: data.streak ?? 0,
    today: data.today ? fromServerCheckIn(data.today) : null,
    checkins: (data.checkins ?? []).map(fromServerCheckIn),
    transitions: (data.transitions ?? []).map(fromServerTransition),
    messages: (data.messages ?? []).map(fromServerMessage),
    phases: data.phases ?? ["IDEA", "VALIDATION", "BUILD", "LAUNCH"],
    canComplete: data.can_complete ?? false,
    archive: (data.archive ?? []).map(fromServerRetirement),
    lifetimeDays: data.lifetime_days ?? 0,
    tone: data.tone,
  };
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

const localDate = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
};

export async function declare(text: string): Promise<CheckIn> {
  const data = await request<ServerCheckIn>("checkins/declare/", {
    method: "POST",
    body: JSON.stringify({ text, date: localDate() }),
  });
  return fromServerCheckIn(data);
}

export async function prove(
  text: string,
  url: string
): Promise<{ checkin: CheckIn; gate: Gate | null; streak: number }> {
  const data = await request<{
    checkin: ServerCheckIn;
    gate: ServerGate;
    streak: number;
  }>("checkins/prove/", {
    method: "POST",
    body: JSON.stringify({ text, url, date: localDate() }),
  });
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
    body: JSON.stringify({ content }),
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
