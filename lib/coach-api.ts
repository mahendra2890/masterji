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
  date: string; // YYYY-MM-DD
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

export type CoachState = {
  goal: Goal | null;
  gate: Gate | null;
  streak: number;
  today: CheckIn | null;
  checkins: CheckIn[];
  transitions: PhaseTransition[];
  messages: ChatMessage[];
  phases: Phase[];
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
type ServerCheckIn = {
  id: number;
  date: string;
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

/** The date window a phase occupied: from the transition that entered it
 * (or the goal's creation, for the first phase) to the transition that
 * left it (or null, if it's the current phase — still open). Powers the
 * stepper drill-in; phases never regress, so each has at most one of each
 * transition. `enteredByTransition` lets the caller attribute a boundary
 * day correctly — check-ins are daily but transitions happen mid-day. */
export function phaseWindow(
  phase: Phase,
  goal: Goal,
  transitions: PhaseTransition[]
): { start: string; end: string | null; enteredByTransition: boolean } {
  const into = transitions.find((t) => t.toPhase === phase);
  const outOf = transitions.find((t) => t.fromPhase === phase);
  return {
    start: into?.createdAt ?? goal.createdAt,
    end: outOf?.createdAt ?? null,
    enteredByTransition: Boolean(into),
  };
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
    tone: data.tone,
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
