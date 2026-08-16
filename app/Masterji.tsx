"use client";

// The two screens, and the branch between them.
//
// Server state is one payload from /api/coach/state/; every mutation returns
// enough to patch it, and chat refetches after a turn. What this file holds is
// that payload, the busy/error pair every write goes through, and the choice of
// screen — <Onboarding /> before there is a goal, <Dashboard /> once there is.
//
// It used to be all of it: one component, 3,089 lines, whose two early returns
// put 87% of itself in a zone where the Rules of Hooks make a hook call
// illegal. Each screen is a component now, so each owns its own hooks and its
// state dies when the screen does — a goal being retired takes <Dashboard />
// down with it rather than leaving the last idea's drill-in, gate note and
// record rows standing under the next one's title.
//
// Three things stay above the branch, and each because both screens need them:
// the payload, the language switch, and the room. The room is the block both
// screens draw, so its client state is a hook here (useRoom) rather than state
// in either of them. `justRetired` and `pivotFrom` are the other direction —
// written by the dashboard as it closes a goal and read by the onboarding
// screen that replaces it, which is a handover neither screen can hold alone.

import { useCallback, useEffect, useState } from "react";
import Dashboard from "./Dashboard";
import DashboardShell from "./DashboardShell";
import Onboarding from "./Onboarding";
import { useRoom } from "./Workshop";
import { updatePrefs, type SessionUser } from "@/lib/auth-client";
import {
  getState,
  type CoachState,
  type Retirement,
} from "@/lib/coach-api";

export default function Masterji({ user }: { user: SessionUser }) {
  const [state, setState] = useState<CoachState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Phone only: the dashboard and the chat take turns instead of stacking.
  // Here rather than in <Dashboard /> because the room's composer is measured
  // against it as well, and the room is held here.
  //
  // Opens on the conversation. Since the inline commit cards (#326) the chat
  // is where a draft completes and where its press lives, so the pane a
  // builder needs first is the one they talk in. Today stays one tap away as
  // the state view, its pill badges carrying the errands — the default is the
  // whole of this decision (recorded on #277's thread); no card control moved.
  const [pane, setPane] = useState<"today" | "chat">("chat");

  // Which closed goal the next one comes out of, set by "Same problem, new
  // idea" and spent by the commit. Client-side only and deliberately not
  // durable: it is a link the builder just asked for, and a flag that survived
  // a closed tab would silently attach last month's idea to a goal they came
  // back and committed for a different reason.
  const [pivotFrom, setPivotFrom] = useState<number | null>(null);
  const [justRetired, setJustRetired] = useState<Retirement | null>(null);

  // Returns the state it fetched as well as storing it: a caller that has to
  // describe the situation it just created (onAdvance) needs the situation,
  // and reading `state` back after an await gives it the one from before.
  const refresh = useCallback(async (): Promise<CoachState | null> => {
    try {
      const next = await getState();
      setState(next);
      return next;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something broke.");
      return null;
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const room = useRoom({
    refresh,
    logLength: state?.workshop?.messages.length,
    shown: pane,
  });

  const run = async (fn: () => Promise<void>) => {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something broke.");
    } finally {
      setBusy(false);
    }
  };

  // The same frame AuthGate was already painting, so the handover from "we are
  // asking who you are" to "we are fetching your goal" changes nothing on
  // screen. This used to be a centred line of text in a full-width <main>,
  // which React reuses as the dashboard's <main> — one element, two classes,
  // and an 80px sideways jump of the whole viewport when the second one won.
  // That was every bit of this route's 0.0625 CLS (#241).
  if (!state) return <DashboardShell />;

  // Null until the builder's first turn: reading state never opens a room. It
  // is the pre-goal room on the onboarding screen and this goal's one
  // reopening on the dashboard — the same endpoint, the same transcript, the
  // same meter, and the server decides which from the builder's own state.
  const ws = state.workshop;
  const roomTurnsLeft = ws ? ws.turnsLeft : state.workshopTurns;

  /** Everything the room reaches out of this component for, gathered once
   * because the two screens that draw it differ in exactly one prop —
   * `reopened` — and spelling the other thirteen out twice is how the two
   * rooms would start to drift.
   *
   * The width of it is the point of the extraction, not a cost of it: this is
   * how much of the parent the room was silently holding when it was a closure
   * in the render body. */
  const roomProps = {
    ws,
    roomTurnsLeft,
    workshopTurns: state.workshopTurns,
    workshopOpeners: state.workshopOpeners,
    ...room,
  };

  // The branch, and the whole of what this component decides. Read off a local
  // rather than `state.goal` so the narrowing survives into the prop: the
  // dashboard is the screen that cannot exist without a goal, and this is the
  // one place that fact is established.
  const goal = state.goal;

  if (!goal)
    return (
      <Onboarding
        state={state}
        busy={busy}
        error={error}
        run={run}
        refresh={refresh}
        justRetired={justRetired}
        pivotFrom={pivotFrom}
        setPivotFrom={setPivotFrom}
        room={roomProps}
      />
    );

  return (
    <Dashboard
      user={user}
      state={state}
      goal={goal}
      busy={busy}
      error={error}
      setError={setError}
      run={run}
      refresh={refresh}
      setState={setState}
      pane={pane}
      setPane={setPane}
      room={roomProps}
      onRetired={(retirement, pivot) => {
        setPivotFrom(pivot);
        setJustRetired(retirement);
      }}
    />
  );
}
