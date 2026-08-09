"use client";

// The whole app in one client component (house convention): a dashboard
// column (goal, phase gate, daily loop, history) and the chat with
// Masterji. Server state is one payload from /api/coach/state/; every
// mutation returns enough to patch it, and chat refetches after a turn.

import { useCallback, useEffect, useRef, useState } from "react";
import { signOutAndLeave } from "@/components/AuthGate";
import FailedTries from "@/components/FailedTries";
import Changelog from "@/components/Changelog";
import ClosedIdea from "./ClosedIdea";
import DayDetail from "./DayDetail";
import { updatePrefs, type SessionUser } from "@/lib/auth-client";
import {
  advanceGoal,
  ApiError,
  createGoal,
  declare,
  judgeDeclaration,
  getState,
  phaseWindow,
  prove,
  retireGoal,
  streamChat,
  type CheckIn,
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

/** Whether the return key should send the reply, or make a line.
 *
 * "Enter sends, Shift+Enter breaks the line" is a hardware-keyboard bargain,
 * and a soft keyboard can't hold up its end: there is no Shift to hold, so
 * the only newline key a phone has was the send button. Tapping the ⏎ icon —
 * which draws itself as a line break, and is the one key there for starting a
 * paragraph — fired the reply off half-written. What gets typed in that box is
 * a night's thinking, so a second paragraph is the normal case, not an edge
 * one, and losing the first one to a keystroke costs the builder the whole
 * point of the box.
 *
 * So ask for the hardware instead of guessing at the screen: a pointer that
 * is fine and hovers is a mouse or a trackpad, and a device driven by one has
 * a Shift key to pair with Enter. Everywhere else the return key does what
 * its icon says and Send is what sends — which is the only affordance a phone
 * had all along. Deliberately not a width test: a desktop window dragged
 * narrow still has the keyboard, and a tablet held wide still doesn't.
 *
 * Asked at the keypress rather than read once at mount, which costs nothing at
 * this rate and means there is no matchMedia call during SSR, no state to
 * hydrate, and no stale answer for an iPad that has since been put in a
 * keyboard case.
 */
const enterSends = () =>
  window.matchMedia("(hover: hover) and (pointer: fine)").matches;

/** The gate situation a note was an answer to.
 *
 * "Not yet, 0/1" stops being true the moment a proof lands, and the card used
 * to keep saying it — under a bar that had since filled, which is the worst
 * sentence to be reading at the best moment in the product. Pinning each
 * answer to the state that produced it lets the card tell that it has been
 * overtaken instead of asserting a refusal the database no longer agrees with.
 *
 * The goal id is in it because this component survives a goal ending: retiring
 * takes the render down the no-goal branch without unmounting, so a refusal
 * left over from the last idea would match a brand-new goal standing in IDEA
 * at 0 proofs and greet it with a refusal it never earned.
 */
const gateKey = (s: CoachState | null) =>
  s?.goal ? `${s.goal.id}:${s.goal.phase}:${s.gate?.have ?? 0}` : "";

/** A day's verdict in one glyph, for the compact rows. Same shape as
 * CLOSED_CHIP above — a property access, not a string lookup, so a renamed
 * class is a type error rather than an undefined className at runtime. */
const CHIP: Record<
  CheckIn["proofStatus"],
  { glyph: string; className: (s: Record<string, string>) => string }
> = {
  ACCEPTED: { glyph: "✓", className: (s) => s.chipGood },
  PUSHED_BACK: { glyph: "✗", className: (s) => s.chipBad },
  NONE: { glyph: "…", className: (s) => s.chipNone },
};

/** One line of the record, and the way into that day.
 *
 * A row is a summary, so it has to open: the proof, the screenshot and
 * Masterji's reaction are all on the check-in and were reachable from
 * nowhere. Shared by the sidebar record and the phase drill-in, which show
 * the same rows and must open the same thing. */
function HistoryRow({ checkin: c, onOpen }: { checkin: CheckIn; onOpen: () => void }) {
  return (
    <li className={styles.historyItem}>
      <button className={styles.historyRow} onClick={onOpen} title="Open this day">
        <span className={styles.historyDate}>{c.date.slice(5)}</span>
        <span className={styles.historyText}>{c.amDeclaration || "—"}</span>
        <span className={CHIP[c.proofStatus].className(styles)}>
          {CHIP[c.proofStatus].glyph}
        </span>
      </button>
    </li>
  );
}

/** The pieces tonight's draft still owes, as the server listed them — one
 * phrase per piece, semicolons between. Split in one place because two screens
 * read it: the Today card lists them, and the line over the composer counts
 * them for a builder who is on the other pane. */
const missingPieces = (missing: string) =>
  missing
    .split(";")
    .map((piece) => piece.trim())
    .filter(Boolean);

/** What tonight's proof has to contain: the tailored ask when the model wrote
 * one, the phase's standing ask when it couldn't, and a worked example behind
 * a disclosure for the builder who reads the rule and still doesn't know what
 * to type.
 *
 * `folded` is the evening where Masterji has already written a draft that
 * clears the bar. The rule is reference then, not instruction — and left open
 * it sat between the answer and the box the answer goes into. Folded rather
 * than dropped: a builder who wants to check his draft against the ask can
 * still open it. */
function ProofAsk({
  ask,
  examples,
  folded,
}: {
  ask: string;
  examples: string[];
  folded: boolean;
}) {
  const body = (
    <>
      <p>{ask}</p>
      {examples.length > 0 && (
        <details className={styles.proofExamples}>
          <summary>Show me one that was accepted</summary>
          {examples.map((ex, i) => (
            <p key={i} className={styles.proofExample}>
              {ex}
            </p>
          ))}
        </details>
      )}
    </>
  );
  if (!folded) return <div className={styles.proofHint}>{body}</div>;
  return (
    <details className={styles.proofHint}>
      <summary className={styles.proofHintSummary}>
        What tonight needs, in full
      </summary>
      {body}
    </details>
  );
}

export default function Masterji({ user }: { user: SessionUser }) {
  const [state, setState] = useState<CoachState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // chat
  // Masterji is reading this morning's task. Not part of `busy`: the form
  // stays fully usable while it runs.
  const [judging, setJudging] = useState(false);
  const declaring = useRef(false);
  const [draft, setDraft] = useState("");
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [pendingUserMsg, setPendingUserMsg] = useState<string | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  // The box you talk back in, so it can be measured against what's in it.
  const composerRef = useRef<HTMLTextAreaElement>(null);

  // Phone only: the dashboard and the chat take turns instead of stacking.
  const [pane, setPane] = useState<"today" | "chat">("today");

  // forms
  const [goalTitle, setGoalTitle] = useState("");
  const [amText, setAmText] = useState("");
  const [pmText, setPmText] = useState("");
  const [pmUrl, setPmUrl] = useState("");
  const [pmImage, setPmImage] = useState<File | null>(null);
  // The evening's box, so the button that fills it can put the caret in it.
  const pmBoxRef = useRef<HTMLTextAreaElement>(null);
  // The gate's last answer, and the situation it answered. Rendered only
  // while the two still match — see gateKey above.
  const [gateNote, setGateNote] = useState<{ text: string; key: string } | null>(
    null
  );

  // The stepper drill-in: which completed phase is being reviewed, if any.
  const [viewPhase, setViewPhase] = useState<Phase | null>(null);
  // A single day of the record, opened from a row. Stacks over the phase
  // drill-in rather than replacing it — the phase list is where the reader
  // was, and closing one day shouldn't cost them their place in it.
  const [viewDay, setViewDay] = useState<CheckIn | null>(null);
  // Opening a second cycle after today's proof already landed.
  const [declaringAgain, setDeclaringAgain] = useState(false);
  // Retiring the current goal: the form, and what Masterji said about it.
  const [retiring, setRetiring] = useState(false);
  const [retireReason, setRetireReason] = useState("");
  const [justRetired, setJustRetired] = useState<Retirement | null>(null);
  // A closed idea being read back — available while a new goal is running.
  const [viewClosed, setViewClosed] = useState<Retirement | null>(null);

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

  // Pin the log to the newest message by scrolling the log itself.
  // scrollIntoView walks up to the nearest scrollable ancestor, and on a
  // phone — where the log only becomes its own scroll box once the chat
  // pane is showing — that ancestor is the page: every load dropped the
  // builder at the very bottom of it, below the whole dashboard.
  useEffect(() => {
    const box = messagesRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [state?.messages.length, streamingText, pane]);

  // The composer is the height of what's in it: one row while it's empty, a
  // row taller for every line typed into it, scrolling once it reaches the cap
  // in CSS. Any fixed height is wrong in both directions at once — it sits
  // there as an empty slab on the screen whose whole point is the conversation
  // above it, and it still hides the line after the last one it has room for.
  //
  // Re-pinning the log is half the job, not a garnish. The log is the flex
  // child that gives up whatever the box takes, so a box growing by a line
  // slides the newest message up under it: you'd watch Masterji's reply leave
  // the screen as you typed your answer to it. Only re-pins a log that was
  // already at the bottom — a builder who scrolled up to re-read something
  // keeps their place.
  const fitComposer = useCallback(() => {
    const box = composerRef.current;
    // display:none, which is how the phone hides whichever pane isn't showing.
    // Nothing to measure there, and measuring anyway writes a 0px height onto
    // the box that the builder then meets when they switch to it.
    if (!box || !box.offsetParent) return;
    const log = messagesRef.current;
    const pinned =
      !!log && log.scrollHeight - log.scrollTop - log.clientHeight < 4;
    // Measured back at one row rather than at whatever the last keystroke left
    // it: scrollHeight can't report less than the height already set on the
    // element, so a box that had been tall once could only ever stay tall.
    box.style.height = "auto";
    // scrollHeight counts padding but not border, and box-sizing is border-box
    // repo-wide, so the height we set has to carry the border itself. Read off
    // the element rather than written as 2px — the border is CSS's to change.
    box.style.height = `${box.scrollHeight + box.offsetHeight - box.clientHeight}px`;
    if (log && pinned) log.scrollTop = log.scrollHeight;
  }, []);

  // Fit the box when it attaches, not only when the draft changes. The chat
  // section unmounts with the goal — retire, land on onboarding, commit a new
  // one — and `draft` outlives that, because the only thing that clears it is
  // sending. So the box can come back holding five lines with the one row
  // `rows` gives a fresh element, and nothing below would re-run: none of that
  // effect's deps changed. It would sit a row tall, hiding a draft the builder
  // never lost, until the next keystroke.
  const attachComposer = useCallback(
    (el: HTMLTextAreaElement | null) => {
      composerRef.current = el;
      if (el) fitComposer();
    },
    [fitComposer]
  );

  // `pane` because the phone mounts this box inside a display:none pane and
  // there is nothing to measure until it shows; window resize because how many
  // lines a paragraph wraps to is a function of width, and a phone turned on
  // its side re-wraps every one of them.
  useEffect(() => {
    fitComposer();
  }, [draft, pane, fitComposer]);

  useEffect(() => {
    window.addEventListener("resize", fitComposer);
    return () => window.removeEventListener("resize", fitComposer);
  }, [fitComposer]);

  // Escape closes the phase drill-in. DayDetail — which opens ON TOP of it —
  // has always had this; the panel underneath never did, so the way out was
  // the × or a click on whatever overlay was still showing. Stands down while
  // a day is open so one Escape closes the top panel, not both at once.
  useEffect(() => {
    if (!viewPhase || viewDay) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setViewPhase(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [viewPhase, viewDay]);

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
      // `disabled={busy}` can't guard this alone — setBusy is async, so two
      // clicks in one tick both get through. The DB constraint keeps that
      // idempotent, but declaring also CLEARS the judgement fields, so a
      // second write landing after the judge response would erase Masterji's
      // read of the task. A ref flips synchronously; state doesn't.
      if (!amText.trim() || declaring.current) return;
      declaring.current = true;
      try {
        const checkin = await declare(amText.trim());
        setAmText("");
        setDeclaringAgain(false);
        await refresh();
        // Outside the awaited path on purpose: the task is already on the
        // record and the form is already usable. Masterji's read of it
        // arrives when it arrives, and a failure here leaves the check-in
        // UNJUDGED rather than leaving the builder staring at a spinner.
        setJudging(true);
        judgeDeclaration(checkin.id)
          .then(refresh)
          // Swallowed deliberately, not dropped: the failure IS the UNJUDGED
          // state the form already handles. Surfacing it as an error would
          // report a broken declaration that isn't broken. The server logs it.
          .catch(() => {})
          .finally(() => setJudging(false));
      } finally {
        declaring.current = false;
      }
    });

  const onProve = () =>
    run(async () => {
      if (!pmText.trim()) return;
      await prove(pmText.trim(), pmUrl.trim(), pmImage);
      setPmText("");
      setPmUrl("");
      setPmImage(null);
      await refresh();
    });

  const onAdvance = () =>
    run(async () => {
      if (!state?.goal) return;
      setGateNote(null);
      let detail: string;
      try {
        detail = (await advanceGoal(state.goal.id)).detail;
      } catch (e) {
        // 409 = the gate said no; its message IS the feature.
        if (e instanceof ApiError && e.status === 409) detail = e.message;
        else throw e;
      }
      // Stamped with the state AFTER the answer, not before it: an advance
      // moves the phase and a refusal doesn't, so this is the only stamp that
      // makes the note last exactly as long as what it describes.
      setGateNote({ text: detail, key: gateKey(await refresh()) });
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

  // Sets a named language rather than flipping the current one — same shape as
  // onSetMode below, and for the same reason: the control is two options with
  // one lit, so "the one I pressed" is all a press can mean.
  const onSetTone = (next: CoachState["tone"]) =>
    run(async () => {
      if (state?.tone === next) return;
      await updatePrefs({ tone: next });
      setState((s) => (s ? { ...s, tone: next } : s));
    });

  // Persisted on the user, not held in this component: a builder who asked to
  // think out loud on their phone should still be in that mode on their laptop.
  //
  // Sets a named mode rather than flipping the current one: the control is two
  // options with one lit, so "the mode I clicked" is the only thing a click can
  // mean. Re-picking the mode already running is a no-op, not a round-trip.
  const onSetMode = (next: CoachState["mode"]) =>
    run(async () => {
      if (state?.mode === next) return;
      await updatePrefs({ mode: next });
      setState((s) => (s ? { ...s, mode: next } : s));
    });

  const onSend = async () => {
    const content = draft.trim();
    if (!content || streamingText !== null) return;
    setDraft("");
    setError("");
    setPendingUserMsg(content);
    setStreamingText("");
    // Whether Masterji got a word out before it fell over. Decides who owns
    // reporting a broken turn — see onError.
    let spoke = false;
    try {
      await streamChat(content, {
        onDelta: (text) => {
          spoke = true;
          setStreamingText((s) => (s ?? "") + text);
        },
        onGate: (gate) =>
          setStreamingText((s) => `${s ?? ""}\n\n${gate.detail}`.trim()),
        // Only when the transcript won't carry it. A turn that died before
        // its first word is saved as this exact sentence server-side (`if
        // broke and not content`), so the banner would put it twice on one
        // screen — once in the log being read, once in a corner above it.
        // A turn that broke PART of the way through is saved as far as it
        // got and no further: the log ends mid-answer with nothing to say
        // it was cut off, and the banner is the only thing that tells the
        // builder to try again rather than read a truncated instruction as
        // the whole one.
        onError: (detail) => {
          if (spoke) setError(detail);
        },
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
                <li key={r.id}>
                  <button
                    className={styles.archiveButton}
                    onClick={() => setViewClosed(r)}
                    title="See how this one went"
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

        <div className={styles.onboardFooter}>
          <button className={styles.linkBtn} onClick={signOutAndLeave}>
            sign out
          </button>
          <Changelog />
        </div>

        {viewClosed && (
          <ClosedIdea closed={viewClosed} onClose={() => setViewClosed(null)} />
        )}
      </main>
    );
  }

  const { goal, gate, streak, today, checkins, transitions, messages, phases, guidance } =
    state;
  void justRetired; // consumed by the no-goal branch above
  const doneIdx = phases.indexOf(goal.phase);
  // Today's loop is still open — worth a dot on the pane you can't see.
  const dayOpen =
    !today?.amDeclaration ||
    !today.pmProofText ||
    today.proofStatus === "PUSHED_BACK";
  // A FINISHED proof Masterji drafted out of the conversation and nobody has
  // filed. Distinct from dayOpen on purpose: dayOpen is lit from the moment the
  // day starts, so it cannot announce anything that arrives mid-day.
  //
  // Running notes deliberately don't light it. The dot means "there is
  // something on the other pane for you to do", and notes are the evening's
  // working-out — they'd relight it on nearly every turn and teach the builder
  // that the dot means nothing.
  const draftWaiting = dayOpen && Boolean(today?.proofOffer) && !today?.proofMissing;
  // Notes still being gathered: he has part of tonight's proof written down and
  // has said which pieces are outstanding. Not draftWaiting — there is nothing
  // to file yet — but emphatically not nothing, which is what the chat pane
  // told the builder for as long as this state existed. The whole point of
  // running notes is that they can SEE they were heard, and the one surface
  // they were looking at while being heard denied it.
  const owed = today?.proofMissing ? missingPieces(today.proofMissing) : [];
  const notesRunning = dayOpen && Boolean(today?.proofOffer) && owed.length > 0;

  const showPane = (next: "today" | "chat") => {
    setPane(next);
    // The dashboard is several screens tall, and the chat pane pins itself
    // to the viewport — leftover page scroll would land on a cropped header.
    window.scrollTo(0, 0);
  };

  return (
    <main className={styles.app} data-pane={pane}>
      <header className={styles.header}>
        <span className={styles.brand}>
          Masterji <span className={styles.brandHindi}>मास्टरजी</span>
        </span>
        <div className={styles.headerRight}>
          {/* The mode used to sit here, next to the language toggle, on the
              grounds that both are "how Masterji talks to you". They aren't
              the same kind of setting. Language is picked once and forgotten;
              the mode is reached for mid-conversation, at the moment the
              replies stop fitting the problem — so it now lives over the
              composer, with the conversation it governs. This corner is
              account chrome, and nobody looks for a way of talking in it. */}
          {/* Both languages on screen, the live one lit — the same fix the
              mode switch got, for the same reason. A single button reading
              "EN" states the language you already have and never reveals that
              the other one exists; Hinglish is half of what makes him
              Masterji, and it was reachable only by pressing a button whose
              label gave no reason to press it. */}
          <div className={styles.toneSwitch} role="group" aria-label="Coach language">
            <button
              type="button"
              className={state.tone === "ENGLISH" ? styles.toneOptOn : styles.toneOpt}
              aria-pressed={state.tone === "ENGLISH"}
              disabled={busy}
              onClick={() => onSetTone("ENGLISH")}
            >
              EN
            </button>
            <button
              type="button"
              lang="hi"
              className={state.tone === "HINGLISH" ? styles.toneOptOn : styles.toneOpt}
              aria-pressed={state.tone === "HINGLISH"}
              disabled={busy}
              onClick={() => onSetTone("HINGLISH")}
            >
              हिं
            </button>
          </div>
          {/* A run that is going, and a run that was. The zero on its own was
              the whole message after a missed day — and a bare zero reads as
              "none of it happened" at exactly the moment quitting looks
              reasonable. The best run is already on the record; it just never
              reached the screen where it would do some good. */}
          {streak > 0 ? (
            <span
              className={styles.streak}
              title="Consecutive complete days on this goal"
            >
              {streak} day{streak === 1 ? "" : "s"} 🔥
            </span>
          ) : state.bestStreak > 0 ? (
            <span
              className={styles.streakCold}
              title="Current run · longest run on this goal"
            >
              0 · best {state.bestStreak}
            </span>
          ) : (
            <span
              className={styles.streakCold}
              title="Declare and prove on the same day to start the run"
            >
              no run yet
            </span>
          )}
          {/* Survives retiring a goal — the streak is about this idea, the
              lifetime count is about the builder. */}
          {state.lifetimeDays > streak && (
            <span className={styles.lifetime} title="Days worked across every goal">
              {state.lifetimeDays} total
            </span>
          )}
          <span className={styles.who}>{user.username}</span>
          <Changelog />
          <button className={styles.linkBtn} onClick={signOutAndLeave}>
            sign out
          </button>
        </div>
      </header>

      {/* role="alert" because this appears without anyone moving focus to
          it, and on a phone it lands above the pane switcher where it is
          easy to miss even when you can see. */}
      {error && (
        <p className={styles.errorBanner} role="alert">
          {error}
        </p>
      )}

      {/* Phone only (hidden ≥821px, where both columns are on screen at
          once). Stacked, the dashboard and a full chat log made a page four
          screens tall with the day's task buried in the middle of it. */}
      <nav className={styles.panes}>
        <button
          className={pane === "today" ? styles.paneOn : styles.pane}
          aria-pressed={pane === "today"}
          onClick={() => showPane("today")}
        >
          Today
          {/* A drafted proof gets a word of its own. The dot can't carry it:
              it is already lit from the moment the day opens, so the one
              event worth crossing panes for was the one event that changed
              nothing on the tab the builder was looking at. */}
          {pane !== "today" &&
            (draftWaiting ? (
              <span className={styles.paneBadge}>draft</span>
            ) : notesRunning ? (
              /* Notes get a word too, and a quieter one. The dot was ruled out
                 for them because it would relight every turn; this doesn't —
                 it is lit by a STATE ("he has some of tonight's proof"), so it
                 comes on with the first piece and stays put until the last.
                 Outlined rather than filled: worth knowing, not an errand. */
              <span className={styles.paneNotes}>notes</span>
            ) : dayOpen ? (
              <span className={styles.paneDot} aria-hidden="true" />
            ) : null)}
        </button>
        <button
          className={pane === "chat" ? styles.paneOn : styles.pane}
          aria-pressed={pane === "chat"}
          onClick={() => showPane("chat")}
        >
          Masterji
        </button>
      </nav>

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
                  // role="button" and a tabindex made this reachable by
                  // keyboard and left it impossible to press — the one
                  // combination worse than not being focusable at all.
                  onKeyDown={
                    i < doneIdx
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setViewPhase(p);
                          }
                        }
                      : undefined
                  }
                  role={i < doneIdx ? "button" : undefined}
                  tabIndex={i < doneIdx ? 0 : undefined}
                  title={i < doneIdx ? `See what happened in ${p}` : undefined}
                >
                  {p}
                </li>
              ))}
            </ol>
            <p className={styles.phaseHint}>{guidance?.phaseHint}</p>

            {gate && gate.need > 0 && (
              <>
                <div className={styles.gateRow}>
                  <span>
                    {/* Capped at the bar. The count is progress toward a
                        requirement, and progress past it is not "8/3" — a
                        builder who kept working read a fraction that looks
                        like a bug on the screen that is supposed to be
                        telling them they're ahead. The surplus is real work,
                        so it still gets said; just not as the numerator. */}
                    <strong>{Math.min(gate.have, gate.need)}</strong>/{gate.need}{" "}
                    proofs toward {gate.nextPhase}
                    {gate.have > gate.need && (
                      <span className={styles.gateExtra}>
                        {" "}
                        · {gate.have - gate.need} more banked
                      </span>
                    )}
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
                {/* The bar being met is the one moment this whole product
                    exists to produce, and it used to look exactly like 0/3:
                    same outlined button, same words, nothing said. A builder
                    could stand here for days having already earned the next
                    phase and never be told. Refusals got ninety words; this
                    got none. */}
                {gate.have >= gate.need ? (
                  <>
                    <p className={styles.gateEarned}>
                      Earned. {gate.nextPhase} is yours to open.
                    </p>
                    <button
                      className={styles.primaryBtn}
                      disabled={busy}
                      onClick={onAdvance}
                    >
                      Open {gate.nextPhase}
                    </button>
                  </>
                ) : (
                  /* Still pressable below the bar, on purpose: Django counts
                     the rows and answers, and being told exactly what is
                     missing is the coaching. */
                  <button
                    className={styles.secondaryBtn}
                    disabled={busy}
                    onClick={onAdvance}
                  >
                    Request phase advance
                  </button>
                )}
              </>
            )}
            {/* Only while it is still an answer to the situation on screen —
                see gateKey. A refusal that outlived the proof that answered
                it used to sit here under a full bar, contradicting the
                counter directly above it. */}
            {gateNote && gateNote.key === gateKey(state) && (
              <p className={styles.gateNote}>{gateNote.text}</p>
            )}

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
                {/* The morning after a broken run. The header carries the
                    number; this carries the only thing worth saying about it,
                    on the card where the answer is a single sentence away.
                    Says what the record shows and points forward — a builder
                    who has already missed two days does not need a third
                    voice telling them so. */}
                {streak === 0 && state.bestStreak > 0 && (
                  <p className={styles.comeback}>
                    Best run on this idea: {state.bestStreak} day
                    {state.bestStreak === 1 ? "" : "s"}. Today is day one of the
                    next one.
                  </p>
                )}
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
                <FailedTries attempts={today.attempts} />
                {/* What Masterji made of this morning's task. Off-phase work
                    is flagged, never blocked — the phase gate is what makes
                    a day spent sideways cost something, not this line. */}
                {today.declarationReaction && (
                  <p
                    className={
                      today.declarationFit === "OFF_PHASE"
                        ? styles.offPhase
                        : styles.sharpen
                    }
                  >
                    {today.declarationReaction}
                  </p>
                )}
                {judging && !today.declarationReaction && (
                  <p className={styles.judging}>Masterji is reading it…</p>
                )}
                {/* Masterji's own draft, written from work the builder already
                    described in chat. It says "you've already told me — here
                    it is", and while pieces are still owed it is notes rather
                    than an offer — the same words, doing a different job. This
                    is the only place the builder can SEE that he heard them,
                    which is the whole reason they stop saying it twice, and it
                    has to show the gap in the same breath or a half-finished
                    draft reads as one that's ready to file.

                    ABOVE the ask, not below it. This is the answer and the ask
                    is the question; a card that puts the question first makes
                    the builder read a rule they have already satisfied before
                    it will show them the words that satisfy it. Filed unedited
                    a complete draft skips a second judgement server-side, so
                    the button copies it verbatim rather than reformatting. */}
                {today.proofOffer && (
                  <div className={styles.proofOffer}>
                    <p className={styles.proofOfferLabel}>
                      {today.proofMissing
                        ? "What Masterji has from your conversation so far"
                        : "Masterji wrote this from your conversation"}
                    </p>
                    <p className={styles.proofOfferText}>{today.proofOffer}</p>
                    {owed.length > 0 && (
                      <div className={styles.proofGap}>
                        <p className={styles.proofGapLabel}>Still needed tonight</p>
                        <ul className={styles.proofGapList}>
                          {owed.map((piece, i) => (
                            <li key={i}>{piece}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <button
                      className={styles.proofOfferBtn}
                      onClick={() => {
                        setPmText(today.proofOffer);
                        // And put them in the box it filled. The draft sits
                        // above the ask now, so the textarea is further down
                        // the card than the button that fills it — a press
                        // whose effect happens off-screen is a press that
                        // reads as broken, and this is the one press in the
                        // card that can end the evening.
                        pmBoxRef.current?.focus();
                      }}
                    >
                      {today.proofMissing
                        ? "Start from these — add the rest below"
                        : "Use this — edit it below if it’s not right"}
                    </button>
                  </div>
                )}
                {(today.proofAsk || guidance) && (
                  <ProofAsk
                    ask={today.proofAsk || guidance?.proofHint || ""}
                    examples={guidance?.proofExamples ?? []}
                    folded={draftWaiting}
                  />
                )}
                <textarea
                  ref={pmBoxRef}
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
                {/* Only offered when the bucket is actually wired, so the form
                    never promises to take something the server would drop. */}
                {state.uploadsEnabled && (
                  <label className={styles.attach}>
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      onChange={(e) => setPmImage(e.target.files?.[0] ?? null)}
                    />
                    <span>
                      {pmImage ? `📎 ${pmImage.name}` : "📎 Attach a screenshot"}
                    </span>
                  </label>
                )}
                <button
                  className={styles.primaryBtn}
                  disabled={busy}
                  onClick={onProve}
                >
                  {busy && pmImage ? "Masterji is looking…" : "Submit proof"}
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
                {today.proofImageUrl && (
                  /* eslint-disable-next-line @next/next/no-img-element --
                     next/image can't optimise a presigned URL that changes
                     every read, and the host isn't known at build time. */
                  <img
                    className={styles.proofImage}
                    src={today.proofImageUrl}
                    alt="The screenshot submitted as proof"
                  />
                )}
                {/* Only the proof that stands is shown above; the misses
                    fold away here rather than reading as part of it. */}
                <FailedTries attempts={today.attempts} />
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
                  <HistoryRow key={c.id} checkin={c} onOpen={() => setViewDay(c)} />
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
          <div className={styles.messages} ref={messagesRef}>
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
          </div>
          {/* Both boxes in this app take the same free text and do entirely
              different things with it: this one records a conversation, the
              one under Today records the day and is the only one the gate
              ever counts. Nothing said so, which is how an evening's real
              work ends up described here and filed nowhere. */}
          <div className={styles.composer}>
            {/* Both modes on screen, one lit. The old control was a single
                button carrying the word "Coach", which states the mode you
                are in and leaves the mode you'd get to be inferred — and
                which never revealed that a second mode existed at all. A
                builder who has never heard of the thinking partner has no
                reason to press a button already labelled with what they've
                got. Two options can't hide the other one.

                Written from the builder's side of the table, because that is
                what the setting actually moves: not "which hat is Masterji
                wearing" but "which of these two do I want done to me". */}
            <div className={styles.modeBar}>
              <div
                className={styles.modeSwitch}
                role="group"
                aria-label="How Masterji talks to you"
              >
                <button
                  type="button"
                  className={
                    state.mode === "COACH" ? styles.modeOptOn : styles.modeOpt
                  }
                  aria-pressed={state.mode === "COACH"}
                  disabled={busy}
                  onClick={() => onSetMode("COACH")}
                >
                  Coach me
                </button>
                <button
                  type="button"
                  className={
                    state.mode === "THINKING" ? styles.modeOptOn : styles.modeOpt
                  }
                  aria-pressed={state.mode === "THINKING"}
                  disabled={busy}
                  onClick={() => onSetMode("THINKING")}
                >
                  Think with me
                </button>
              </div>
              {/* The sentence the tooltip could never give a phone. Names the
                  mode you are in, one clause, and stops.

                  It briefly had a "What's the difference?" disclosure beside
                  it, holding a paragraph on both modes. Removed on Mahendra's
                  call — three text elements in one bar looked like clutter,
                  and the bar is a control, not a help page. So the row is the
                  switch and one clause about the lit mode, and what the other
                  mode is FOR lives in the tour, which has room to say it
                  properly. If that ever needs to be in the product itself,
                  the answer is not a third thing on this line. */}
              <p className={styles.modeCaption}>
                {state.mode === "THINKING"
                  ? "Questions and options, not assignments."
                  : "Assignments and push-back."}
              </p>
            </div>
            <div className={styles.composerRow}>
              <textarea
                ref={attachComposer}
                className={styles.composerInput}
                /* One row is the starting height, not the height. fitComposer
                   grows the box a line at a time as it fills, the way every
                   chat composer a builder has ever used does, up to the cap in
                   CSS. Four fixed rows were an attempt at the same thing with
                   a single number, and a single number can't do it: it was a
                   109px slab of nothing above the conversation while the box
                   was empty, and it still cut the fifth line off anyone whose
                   answer ran to five. `rows` is what's left if the JS hasn't
                   run yet, so it states the resting height rather than the
                   biggest one this could reach. */
                rows={1}
                /* Short on purpose. The rule this box needs to state doesn't
                   fit in it: at 375px the composer clears 205px of text, and
                   the sentence needs 444px — it truncated to "Think out loud
                   — nothing here", which is worse than saying nothing. The
                   rule lives on the line below the box, which can wrap. */
                placeholder={
                  state.mode === "THINKING" ? "Think out loud…" : "Talk it through…"
                }
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && enterSends()) {
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
          </div>
          {/* Where the rule actually lives. A placeholder was the obvious
              home for it and the wrong one twice over: it is clipped to a
              third of itself on a phone, and it disappears the moment they
              start typing — which is exactly when a builder is pouring the
              evening's work into the wrong box. This wraps, and it stays. */}
          {dayOpen && (
            <p
              className={
                draftWaiting
                  ? styles.composerDraft
                  : notesRunning
                    ? styles.composerNotes
                    : styles.composerNote
              }
            >
              {draftWaiting
                ? "Masterji drafted tonight's proof — file it under Today."
                : notesRunning
                  ? /* The standing rule is still true and still said — what
                       changes is that it stops being the whole truth. He is
                       writing this conversation down under Today as it
                       happens; "nothing here counts" on its own read as
                       "you are wasting your breath" at the exact moment the
                       builder was giving him tonight's evidence. */
                    `Masterji is writing this up under Today — ${owed.length} piece${
                      owed.length === 1 ? "" : "s"
                    } still needed. Nothing counts until you file it.`
                  : today?.amDeclaration
                    ? "Nothing here counts until you file it under Today."
                    : "Nothing here counts. Declare today's task under Today first."}
            </p>
          )}
        </section>
      </div>

      {viewClosed && (
        <ClosedIdea closed={viewClosed} onClose={() => setViewClosed(null)} />
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
              <div
                className={styles.modal}
                onClick={(e) => e.stopPropagation()}
                role="dialog"
                aria-modal="true"
                aria-label={`${viewPhase} — the days spent in this phase`}
              >
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
                      <HistoryRow key={c.id} checkin={c} onOpen={() => setViewDay(c)} />
                    ))}
                  </ul>
                )}
              </div>
            </div>
          );
        })()}

      {/* Last, so it layers over the phase drill-in it can be opened from.
          Re-read from `checkins` by id rather than rendered from the stored
          row: a refresh behind the modal (a proof landing, a judgement
          arriving) would otherwise leave the open day showing the version
          that was on screen when it was clicked. */}
      {viewDay && (
        <DayDetail
          checkin={checkins.find((c) => c.id === viewDay.id) ?? viewDay}
          onClose={() => setViewDay(null)}
        />
      )}
    </main>
  );
}
