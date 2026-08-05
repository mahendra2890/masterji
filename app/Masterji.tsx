"use client";

// The whole app in one client component (house convention): a dashboard
// column (goal, phase gate, daily loop, history) and the chat with
// Masterji. Server state is one payload from /api/coach/state/; every
// mutation returns enough to patch it, and chat refetches after a turn.

import { useCallback, useEffect, useRef, useState } from "react";
import { signOutAndLeave } from "@/components/AuthGate";
import { updateTone, type SessionUser } from "@/lib/auth-client";
import {
  advanceGoal,
  ApiError,
  createGoal,
  declare,
  getState,
  phaseWindow,
  prove,
  retireGoal,
  streamChat,
  type CoachState,
  type Phase,
  type Retirement,
} from "@/lib/coach-api";
import styles from "./masterji.module.css";

/** How each closed idea reads, in one chip. The wording states what the record
 * shows, never a judgement of the person. */
const CLOSED_CHIP: Record<
  Retirement["readsAs"],
  { label: string; className: (s: Record<string, string>) => string }
> = {
  ACHIEVED: { label: "achieved", className: (s) => s.chipGood },
  UNVERIFIED: { label: "achieved · unverified", className: (s) => s.chipNone },
  INVALIDATED: { label: "tested → dead", className: (s) => s.chipTested },
  UNTESTED: { label: "untested", className: (s) => s.chipNone },
};

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

const PHASE_HINTS: Record<string, string> = {
  IDEA: "Write the problem statement. Name 10 people who have it.",
  VALIDATION: "Talk to real customers. Bring notes, not opinions.",
  BUILD: "Smallest thing a real user can touch this week.",
  LAUNCH: "In front of strangers. Ask for commitment.",
};

// What actually counts as tonight's proof, spelled out — so nobody has to
// ask Masterji in chat to find out. Mirrors gates.py's proof requirements
// and the phase playbooks; keep these in sync if either changes.
const PROOF_HINTS: Record<string, string> = {
  IDEA: "What to submit: your one-paragraph problem statement + the list of 10 real people who have this problem.",
  VALIDATION:
    "What to submit: notes from ONE real conversation — who you spoke to, 3 things they said in their own words, what they last did about this problem, and what commitment you asked for (and got).",
  BUILD:
    "What to submit: a link to something live, or clear evidence a real user touched it (screenshot, log entry, message).",
  LAUNCH:
    "What to submit: a link to your public post, evidence of a new user's action (or payment), or a real rejection with the reason.",
};

export default function Masterji({ user }: { user: SessionUser }) {
  const [state, setState] = useState<CoachState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // chat
  const [draft, setDraft] = useState("");
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [pendingUserMsg, setPendingUserMsg] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // forms
  const [goalTitle, setGoalTitle] = useState("");
  const [amText, setAmText] = useState("");
  const [pmText, setPmText] = useState("");
  const [pmUrl, setPmUrl] = useState("");
  const [gateNote, setGateNote] = useState("");

  // The stepper drill-in: which completed phase is being reviewed, if any.
  const [viewPhase, setViewPhase] = useState<Phase | null>(null);
  // Opening a second cycle after today's proof already landed.
  const [declaringAgain, setDeclaringAgain] = useState(false);
  // Retiring the current goal: the form, and what Masterji said about it.
  const [retiring, setRetiring] = useState(false);
  const [retireReason, setRetireReason] = useState("");
  const [justRetired, setJustRetired] = useState<Retirement | null>(null);
  // A closed idea being read back — available while a new goal is running.
  const [viewClosed, setViewClosed] = useState<Retirement | null>(null);

  const refresh = useCallback(async () => {
    try {
      setState(await getState());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something broke.");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state?.messages.length, streamingText]);

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

  const onCreateGoal = () =>
    run(async () => {
      if (!goalTitle.trim()) return;
      await createGoal(goalTitle.trim());
      setGoalTitle("");
      await refresh();
    });

  const onDeclare = () =>
    run(async () => {
      if (!amText.trim()) return;
      await declare(amText.trim());
      setAmText("");
      setDeclaringAgain(false);
      await refresh();
    });

  const onProve = () =>
    run(async () => {
      if (!pmText.trim()) return;
      await prove(pmText.trim(), pmUrl.trim());
      setPmText("");
      setPmUrl("");
      await refresh();
    });

  const onAdvance = () =>
    run(async () => {
      if (!state?.goal) return;
      setGateNote("");
      try {
        const result = await advanceGoal(state.goal.id);
        setGateNote(result.detail);
      } catch (e) {
        // 409 = the gate said no; its message IS the feature.
        if (e instanceof ApiError && e.status === 409) {
          setGateNote(e.message);
        } else {
          throw e;
        }
      }
      await refresh();
    });

  const onRetire = (outcome: "ABANDONED" | "COMPLETED") =>
    run(async () => {
      if (!state?.goal || !retireReason.trim()) return;
      const { retirement } = await retireGoal(
        state.goal.id,
        retireReason.trim(),
        outcome
      );
      setRetireReason("");
      setRetiring(false);
      // Hold Masterji's reaction on screen. Without this the dashboard would
      // vanish into an empty "One goal." form the instant the goal closed —
      // the worst possible moment to be handed a blank input.
      setJustRetired(retirement);
      await refresh();
    });

  const onToggleTone = () =>
    run(async () => {
      const next = state?.tone === "HINGLISH" ? "ENGLISH" : "HINGLISH";
      await updateTone(next);
      setState((s) => (s ? { ...s, tone: next } : s));
    });

  const onSend = async () => {
    const content = draft.trim();
    if (!content || streamingText !== null) return;
    setDraft("");
    setError("");
    setPendingUserMsg(content);
    setStreamingText("");
    try {
      await streamChat(content, {
        onDelta: (text) => setStreamingText((s) => (s ?? "") + text),
        onGate: (gate) =>
          setStreamingText((s) => `${s ?? ""}\n\n${gate.detail}`.trim()),
        onError: (detail) => setError(detail),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something broke.");
    } finally {
      await refresh();
      setPendingUserMsg(null);
      setStreamingText(null);
    }
  };

  if (!state) {
    return <main className={styles.loading}>Masterji is on his way…</main>;
  }

  /* --- onboarding / just-retired ---------------------------------------- */
  if (!state.goal) {
    const closing = justRetired ?? state.archive[0];
    const shipped = closing?.outcome === "COMPLETED";
    return (
      <main className={styles.onboarding}>
        <p className={styles.wordmark}>मास्टरजी</p>

        {closing ? (
          <>
            <h1 className={styles.onboardTitle}>
              {shipped ? "Shipped." : "Closed."}
            </h1>
            <p className={styles.closingWhich}>{closing.title}</p>
            <p
              className={
                closing.readsAs === "ACHIEVED" || closing.readsAs === "INVALIDATED"
                  ? styles.closingWin
                  : styles.closingPlain
              }
            >
              {closing.coachReaction}
            </p>
            <p className={styles.closingStats}>
              Reached {closing.phaseReached} · {closing.acceptedProofs} proof
              {closing.acceptedProofs === 1 ? "" : "s"} banked · {closing.daysActive}{" "}
              day{closing.daysActive === 1 ? "" : "s"} active
              {state.lifetimeDays > 0 && (
                <>
                  {" · "}
                  {state.lifetimeDays} day{state.lifetimeDays === 1 ? "" : "s"} of
                  work on your record
                </>
              )}
            </p>
          </>
        ) : (
          <>
            <h1 className={styles.onboardTitle}>One goal.</h1>
            <p className={styles.onboardSub}>
              Masterji coaches one thing at a time — pick the goal that matters
              and commit. You can retire it later, but he&apos;ll remember.
            </p>
          </>
        )}

        <div className={styles.onboardForm}>
          <input
            className={styles.input}
            placeholder={
              closing ? "So — what's next?" : "e.g. Tiffin-delivery app for my college"
            }
            value={goalTitle}
            maxLength={200}
            onChange={(e) => setGoalTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onCreateGoal()}
          />
          <button className={styles.primaryBtn} disabled={busy} onClick={onCreateGoal}>
            Commit
          </button>
        </div>
        {error && <p className={styles.error}>{error}</p>}

        {state.archive.length > 0 && (
          <section className={styles.archive}>
            <p className={styles.cardLabel}>Behind you</p>
            <ul className={styles.archiveList}>
              {state.archive.map((r) => (
                <li key={r.id} className={styles.archiveRow}>
                  <span className={styles.archiveTitle}>{r.title}</span>
                  <span className={CLOSED_CHIP[r.readsAs].className(styles)}>
                    {CLOSED_CHIP[r.readsAs].label}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <button className={styles.linkBtn} onClick={signOutAndLeave}>
          sign out
        </button>
      </main>
    );
  }

  const { goal, gate, streak, today, checkins, transitions, messages, phases } = state;
  void justRetired; // consumed by the no-goal branch above
  const doneIdx = phases.indexOf(goal.phase);

  return (
    <main className={styles.app}>
      <header className={styles.header}>
        <span className={styles.brand}>
          Masterji <span className={styles.brandHindi}>मास्टरजी</span>
        </span>
        <div className={styles.headerRight}>
          <button
            className={styles.toneBtn}
            onClick={onToggleTone}
            title="Coach language"
          >
            {state.tone === "HINGLISH" ? "हिं" : "EN"}
          </button>
          <span className={styles.streak} title="Consecutive complete days on this goal">
            {streak} day{streak === 1 ? "" : "s"} 🔥
          </span>
          {/* Survives retiring a goal — the streak is about this idea, the
              lifetime count is about the builder. */}
          {state.lifetimeDays > streak && (
            <span className={styles.lifetime} title="Days worked across every goal">
              {state.lifetimeDays} total
            </span>
          )}
          <span className={styles.who}>{user.username}</span>
          <button className={styles.linkBtn} onClick={signOutAndLeave}>
            sign out
          </button>
        </div>
      </header>

      {error && <p className={styles.errorBanner}>{error}</p>}

      <div className={styles.columns}>
        {/* ------------------------------------------------ dashboard */}
        <aside className={styles.side}>
          <section className={styles.card}>
            <p className={styles.cardLabel}>The goal</p>
            <h2 className={styles.goalTitle}>{goal.title}</h2>

            <ol className={styles.stepper}>
              {phases.map((p, i) => (
                <li
                  key={p}
                  className={
                    i < doneIdx
                      ? styles.stepDone
                      : i === doneIdx
                        ? styles.stepNow
                        : styles.stepTodo
                  }
                  onClick={i < doneIdx ? () => setViewPhase(p) : undefined}
                  role={i < doneIdx ? "button" : undefined}
                  tabIndex={i < doneIdx ? 0 : undefined}
                  title={i < doneIdx ? `See what happened in ${p}` : undefined}
                >
                  {p}
                </li>
              ))}
            </ol>
            <p className={styles.phaseHint}>{PHASE_HINTS[goal.phase]}</p>

            {gate && gate.need > 0 && (
              <>
                <div className={styles.gateRow}>
                  <span>
                    <strong>{gate.have}</strong>/{gate.need} proofs toward{" "}
                    {gate.nextPhase}
                  </span>
                </div>
                <div className={styles.gateBar}>
                  <div
                    className={styles.gateFill}
                    style={{
                      width: `${Math.min(100, (gate.have / gate.need) * 100)}%`,
                    }}
                  />
                </div>
                <button
                  className={styles.secondaryBtn}
                  disabled={busy}
                  onClick={onAdvance}
                >
                  Request phase advance
                </button>
              </>
            )}
            {gateNote && <p className={styles.gateNote}>{gateNote}</p>}

            {/* At LAUNCH with proof on the record, finishing is the expected
                move, so it gets a real button. Everywhere else it lives behind
                the quiet link — available, just not advertised. */}
            {state.atFinishLine && !retiring && (
              <button
                className={styles.secondaryBtn}
                onClick={() => setRetiring(true)}
              >
                Close this out
              </button>
            )}

            {!retiring ? (
              <button
                className={styles.retireLink}
                onClick={() => setRetiring(true)}
              >
                close this goal
              </button>
            ) : (
              <div className={styles.retireBox}>
                <p className={styles.retirePrompt}>
                  What happened? One honest sentence — it goes on the record.
                </p>
                <textarea
                  className={styles.textarea}
                  rows={3}
                  placeholder="e.g. Site is live and the school is using it for notices — or: talked to 6 students, they won't pay for this."
                  value={retireReason}
                  onChange={(e) => setRetireReason(e.target.value)}
                />
                <div className={styles.retireActions}>
                  {/* Both exits, always. Achieving your goal from BUILD is not
                      a thing the server gets to disallow. */}
                  <button
                    className={styles.primaryBtn}
                    disabled={busy || !retireReason.trim()}
                    onClick={() => onRetire("COMPLETED")}
                  >
                    I achieved it
                  </button>
                  <button
                    className={styles.secondaryBtn}
                    disabled={busy || !retireReason.trim()}
                    onClick={() => onRetire("ABANDONED")}
                  >
                    I&apos;m dropping it
                  </button>
                  <button
                    className={styles.linkBtn}
                    onClick={() => {
                      setRetiring(false);
                      setRetireReason("");
                    }}
                  >
                    keep going
                  </button>
                </div>
              </div>
            )}
          </section>

          <section className={styles.card}>
            <p className={styles.cardLabel}>Today</p>
            {!today?.amDeclaration ? (
              <>
                <p className={styles.todayPrompt}>
                  Morning. One task, out loud:
                </p>
                <textarea
                  className={styles.textarea}
                  rows={2}
                  placeholder="Today I will…"
                  value={amText}
                  onChange={(e) => setAmText(e.target.value)}
                />
                <button
                  className={styles.primaryBtn}
                  disabled={busy}
                  onClick={onDeclare}
                >
                  Declare it
                </button>
              </>
            ) : !today.pmProofText || today.proofStatus === "PUSHED_BACK" ? (
              <>
                <p className={styles.declared}>
                  Declared: <em>{today.amDeclaration}</em>
                </p>
                {today.proofStatus === "PUSHED_BACK" && (
                  <p className={styles.pushedBack}>{today.coachReaction}</p>
                )}
                <p className={styles.proofHint}>{PROOF_HINTS[goal.phase]}</p>
                <textarea
                  className={styles.textarea}
                  rows={3}
                  placeholder="Evening proof — what actually happened?"
                  value={pmText}
                  onChange={(e) => setPmText(e.target.value)}
                />
                <input
                  className={styles.input}
                  placeholder="Link (optional)"
                  value={pmUrl}
                  onChange={(e) => setPmUrl(e.target.value)}
                />
                <button
                  className={styles.primaryBtn}
                  disabled={busy}
                  onClick={onProve}
                >
                  Submit proof
                </button>
              </>
            ) : (
              <>
                <p className={styles.declared}>
                  Declared: <em>{today.amDeclaration}</em>
                </p>
                <p
                  className={
                    today.proofStatus === "ACCEPTED"
                      ? styles.accepted
                      : styles.pushedBack
                  }
                >
                  {today.proofStatus === "ACCEPTED" ? "✓ accepted" : "pushed back"}
                  {" — "}
                  {today.coachReaction}
                </p>
                {/* Done for today doesn't have to mean done for the day. */}
                {!declaringAgain ? (
                  <button
                    className={styles.secondaryBtn}
                    onClick={() => setDeclaringAgain(true)}
                  >
                    Declare another task
                  </button>
                ) : (
                  <>
                    <textarea
                      className={styles.textarea}
                      rows={2}
                      placeholder="Next up, I will…"
                      value={amText}
                      onChange={(e) => setAmText(e.target.value)}
                    />
                    <button
                      className={styles.primaryBtn}
                      disabled={busy}
                      onClick={onDeclare}
                    >
                      Declare it
                    </button>
                  </>
                )}
              </>
            )}
          </section>

          {checkins.length > 0 && (
            <section className={styles.card}>
              <p className={styles.cardLabel}>The record</p>
              <ul className={styles.history}>
                {checkins.map((c) => (
                  <li key={c.id} className={styles.historyRow}>
                    <span className={styles.historyDate}>{c.date.slice(5)}</span>
                    <span className={styles.historyText}>{c.amDeclaration || "—"}</span>
                    <span
                      className={
                        c.proofStatus === "ACCEPTED"
                          ? styles.chipGood
                          : c.proofStatus === "PUSHED_BACK"
                            ? styles.chipBad
                            : styles.chipNone
                      }
                    >
                      {c.proofStatus === "ACCEPTED"
                        ? "✓"
                        : c.proofStatus === "PUSHED_BACK"
                          ? "✗"
                          : "…"}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Closed ideas stay reachable while a new goal is running — the
              record is the point, and it can't do its work if it's only
              visible in the four seconds between goals. */}
          {state.archive.length > 0 && (
            <section className={styles.card}>
              <p className={styles.cardLabel}>Behind you</p>
              <ul className={styles.archiveList}>
                {state.archive.map((r) => (
                  <li key={r.id}>
                    <button
                      className={styles.archiveButton}
                      onClick={() => setViewClosed(r)}
                      title="See how this one ended"
                    >
                      <span className={styles.archiveTitle}>{r.title}</span>
                      <span className={CLOSED_CHIP[r.readsAs].className(styles)}>
                        {CLOSED_CHIP[r.readsAs].label}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>

        {/* ------------------------------------------------ chat */}
        <section className={styles.chat}>
          <div className={styles.messages}>
            {messages.map((m) => (
              <div
                key={m.id}
                className={m.role === "COACH" ? styles.coachMsg : styles.userMsg}
              >
                {m.role === "COACH" && <span className={styles.avatar}>म</span>}
                <p className={styles.msgBody}>{m.content}</p>
              </div>
            ))}
            {pendingUserMsg && (
              <div className={styles.userMsg}>
                <p className={styles.msgBody}>{pendingUserMsg}</p>
              </div>
            )}
            {streamingText !== null && (
              <div className={styles.coachMsg}>
                <span className={styles.avatar}>म</span>
                <p className={styles.msgBody}>
                  {streamingText || <span className={styles.thinking}>…</span>}
                </p>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
          <div className={styles.composer}>
            <textarea
              className={styles.composerInput}
              rows={1}
              placeholder="Talk to Masterji…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSend();
                }
              }}
            />
            <button
              className={styles.primaryBtn}
              disabled={streamingText !== null || !draft.trim()}
              onClick={onSend}
            >
              Send
            </button>
          </div>
        </section>
      </div>

      {viewClosed && (
        <div className={styles.modalOverlay} onClick={() => setViewClosed(null)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h3>{viewClosed.title}</h3>
              <button
                className={styles.modalClose}
                onClick={() => setViewClosed(null)}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <p className={styles.modalMeta}>
              {viewClosed.outcome === "COMPLETED" ? "Achieved" : "Dropped"} on{" "}
              {formatDate(viewClosed.createdAt)} · reached {viewClosed.phaseReached} ·{" "}
              {viewClosed.acceptedProofs} proof
              {viewClosed.acceptedProofs === 1 ? "" : "s"} banked
              {/* The narrower count only earns a mention when it changes the
                  reading — otherwise it reads as a scolding footnote. */}
              {viewClosed.contactProofs > 0 &&
                viewClosed.contactProofs !== viewClosed.acceptedProofs && (
                  <> ({viewClosed.contactProofs} from real-world contact)</>
                )}{" "}
              · {viewClosed.daysActive} day{viewClosed.daysActive === 1 ? "" : "s"} ·
              best streak {viewClosed.bestStreak}
            </p>
            <p className={styles.closedLabel}>What you said</p>
            <p className={styles.closedReason}>{viewClosed.reason}</p>
            {viewClosed.coachReaction && (
              <>
                <p className={styles.closedLabel}>What Masterji said</p>
                <div className={styles.coachMsg}>
                  <span className={styles.avatar}>म</span>
                  <p className={styles.msgBody}>{viewClosed.coachReaction}</p>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {viewPhase &&
        (() => {
          const win = phaseWindow(viewPhase, goal, transitions);
          // Each check-in carries the phase it was made in, stamped
          // server-side. Don't infer it from dates: CheckIn.date is the
          // client's local date while transitions are server UTC, so the
          // two disagree around a late-night advance.
          const windowCheckins = checkins.filter((c) => c.phase === viewPhase);
          return (
            <div className={styles.modalOverlay} onClick={() => setViewPhase(null)}>
              <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
                <div className={styles.modalHeader}>
                  <h3>{viewPhase}</h3>
                  <button
                    className={styles.modalClose}
                    onClick={() => setViewPhase(null)}
                    aria-label="Close"
                  >
                    ×
                  </button>
                </div>
                <p className={styles.modalMeta}>
                  {formatDate(win.start)} — {win.end ? formatDate(win.end) : "now"}
                </p>
                {windowCheckins.length === 0 ? (
                  <p className={styles.modalEmpty}>
                    No check-ins recorded in this phase.
                  </p>
                ) : (
                  <ul className={styles.history}>
                    {windowCheckins.map((c) => (
                      <li key={c.id} className={styles.historyRow}>
                        <span className={styles.historyDate}>{c.date.slice(5)}</span>
                        <span className={styles.historyText}>
                          {c.amDeclaration || "—"}
                        </span>
                        <span
                          className={
                            c.proofStatus === "ACCEPTED"
                              ? styles.chipGood
                              : c.proofStatus === "PUSHED_BACK"
                                ? styles.chipBad
                                : styles.chipNone
                          }
                        >
                          {c.proofStatus === "ACCEPTED"
                            ? "✓"
                            : c.proofStatus === "PUSHED_BACK"
                              ? "✗"
                              : "…"}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          );
        })()}
    </main>
  );
}
