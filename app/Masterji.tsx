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
  streamChat,
  type CoachState,
  type Phase,
} from "@/lib/coach-api";
import styles from "./masterji.module.css";

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

  /* --- onboarding: no goal yet ------------------------------------------ */
  if (!state.goal) {
    return (
      <main className={styles.onboarding}>
        <p className={styles.wordmark}>मास्टरजी</p>
        <h1 className={styles.onboardTitle}>One goal.</h1>
        <p className={styles.onboardSub}>
          Masterji coaches one thing at a time — pick the goal that matters
          and commit. You can abandon it later, but he&apos;ll remember.
        </p>
        <div className={styles.onboardForm}>
          <input
            className={styles.input}
            placeholder="e.g. Tiffin-delivery app for my college"
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
        <button className={styles.linkBtn} onClick={signOutAndLeave}>
          sign out
        </button>
      </main>
    );
  }

  const { goal, gate, streak, today, checkins, transitions, messages, phases } = state;
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
          <span className={styles.streak} title="Consecutive complete days">
            {streak} day{streak === 1 ? "" : "s"} 🔥
          </span>
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
