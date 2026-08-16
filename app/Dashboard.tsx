"use client";

// The main screen: the goal card, the Today card, the record, the chat pane,
// the phase drill-in and the day panel.
//
// Its own component so it owns its own hooks. It used to be the tail of
// `Masterji()`, below two early returns — 87% of that file, and every line of
// it in a zone where the Rules of Hooks made a `useMemo` illegal. The state
// here is declared beside the card that reads it and dies when the goal does,
// because the parent branches to <Onboarding /> and unmounts this whole tree.

import {
  Fragment,
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import FailedTries from "@/components/FailedTries";
import Changelog from "@/components/Changelog";
import TakeTheRecord from "@/components/TakeTheRecord";
import NudgeSwitch from "@/components/NudgeSwitch";
import ClosedIdea from "./ClosedIdea";
import DayDetail from "./DayDetail";
import Workshop, { type RoomProps } from "./Workshop";
import { CLOSED_CHIP, SignOutButton, ToneSwitch, TourLink } from "./chrome";
import { updatePrefs, type SessionUser } from "@/lib/auth-client";
import { useDialogFocus } from "@/lib/dialog-focus";
import { readDraft, writeDraft } from "@/lib/drafts";
import { fitBox } from "@/lib/fit-box";
import {
  dayOpen as isDayOpen,
  draftWaiting as isDraftWaiting,
  eveningOpen as isEveningOpen,
  isUnsettled,
  missingPieces,
  notesRunning as isNotesRunning,
} from "@/lib/day";
import { gateKey, isEarned } from "@/lib/gate";
import {
  cardIndex,
  liveAnchor,
  liveOffer,
  nextAnchor,
  type LiveOffer,
  type OfferAnchor,
} from "@/lib/inline-offer";
import { pinLog } from "@/lib/log-pin";
import { saidBefore } from "@/lib/messages";
import { isSendKey } from "@/lib/send-key";
import {
  anyRepeat as anyRepeatIn,
  cycleOrdinals,
  newestFirst,
  ordinalLabel,
  recordSlice,
  rowsExtent,
} from "@/lib/record";
import {
  advanceGoal,
  ApiError,
  declare,
  formatDay,
  formatDayShort,
  judgeDeclaration,
  getGoalHistory,
  localDate,
  phaseWindow,
  prove,
  retireGoal,
  setPhaseIntent,
  setLaunchDate,
  setMetric,
  streamChat,
  updateGoalTitle,
  type CheckIn,
  type CoachState,
  type Goal,
  type Phase,
  type Retirement,
} from "@/lib/coach-api";
import styles from "./masterji.module.css";

/** How much of the record the card shows before it is asked for the rest —
 * see the comment where it is used. Rows, not days: a builder who declares a
 * second task after proving the first gets two rows for one date, and the card
 * would rather show seven rows than promise seven days and count them wrong. */
const RECORD_PREVIEW = 7;

/** How many readings of the one number fit on the goal card. Four because the
 * card's line is a direction of travel, not the record: the whole series is in
 * the record card underneath, and the coach is handed the last two. */
const METRIC_PREVIEW = 4;
/** Kept in step with views.MetricView.MAX_CHARS. Here so the box stops taking
 * characters the server would refuse, rather than accepting a sentence and
 * bouncing it — the cap is what makes it one metric and not several. */
const METRIC_NAME_MAX = 60;

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

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
  // Neither tick nor cross, because neither happened. The day is on the
  // record; the reading is what's outstanding.
  UNJUDGED: { glyph: "•", className: (s) => s.chipNone },
};

/** An hour of the builder's own day, 00:00–23:00. */
const hourLabel = (h: number) => `${String(h).padStart(2, "0")}:00`;

/** Every hour, not an evening's worth. A day can hold more than one cycle (see
 * "Declare another task") and the second one gets proved whenever it gets
 * proved, so a list that stopped at midnight-ish would be this control holding
 * a product opinion it has no standing to hold. */
const DUE_HOURS = Array.from({ length: 24 }, (_, h) => h);

/** The hour beside "Declare it", and nothing else.
 *
 * It STAYS A CONTROL. No caption, no tooltip, no "why bother" line: this repo
 * puts that in the tour (app/demo/Tour.tsx, slide 2), and the one time an
 * explanation was set down beside a control here it shipped as clutter and was
 * pulled out again — the note under `.modeSwitch` records that. So the strip
 * says what the choice is and the deck says what it buys.
 *
 * What it must never say is that anything will happen AT this hour. Nothing
 * fires on a clock in this product yet, and when something does (#142 settled
 * it as a best-effort GitHub Actions tick, shared with #87) it will arrive
 * shortly after the hour rather than at it. "by 21:00" is the builder's own
 * claim about their evening, which is true with no scheduler at all; "he'll
 * be waiting at 21:00" would be a promise the infrastructure cannot keep. */
function DueHourSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <select
      className={styles.hourSelect}
      aria-label="When tonight's proof will land"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">any time tonight</option>
      {DUE_HOURS.map((h) => (
        <option key={h} value={h}>
          by {hourLabel(h)}
        </option>
      ))}
    </select>
  );
}

/** One line of the record, and the way into that day.
 *
 * A row is a summary, so it has to open: the proof, the screenshot and
 * Masterji's reaction are all on the check-in and were reachable from
 * nowhere. Shared by the sidebar record and the phase drill-in, which show
 * the same rows and must open the same thing.
 *
 * `cycle` is which declare→prove cycle of its own day this row is, and the
 * date alone cannot say it: a day may hold more than one, and the commonest
 * second task is a continuation of the first, so two rows can differ in
 * nothing but their glyph. `showCycle` is the list's decision rather than the
 * row's — the marker gets a column of its own, and a list with no repeat in it
 * should not pay for one on a phone. */
function HistoryRow({
  checkin: c,
  cycle,
  showCycle,
  onOpen,
}: {
  checkin: CheckIn;
  cycle: number;
  showCycle: boolean;
  onOpen: () => void;
}) {
  const repeat = cycle > 1;
  return (
    <li className={styles.historyItem}>
      <button
        className={styles.historyRow}
        onClick={onOpen}
        title={repeat ? `Open this day — ${ordinalLabel(cycle)} cycle` : "Open this day"}
      >
        <span className={styles.historyDate}>{formatDayShort(c.date)}</span>
        {/* Empty on a day's first cycle rather than absent, so the rows of one
            list still align with each other. */}
        {showCycle && (
          <span className={styles.historyCycle}>
            {repeat ? `· ${ordinalLabel(cycle)}` : ""}
          </span>
        )}
        <span className={styles.historyText}>{c.amDeclaration || "—"}</span>
        <span className={CHIP[c.proofStatus].className(styles)}>
          {CHIP[c.proofStatus].glyph}
        </span>
      </button>
    </li>
  );
}

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

/** The commit moment, rendered a second time where the draft was written.
 *
 * The same draft the Today card is showing, with the press in place: `Declare
 * it` under a drafted task, `Submit proof` — link and screenshot included —
 * under tonight's. On a laptop both panes are on screen and this costs nothing;
 * on a phone the panes take turns, and a finished draft used to land in the one
 * the builder was not looking at. Switch, hunt, press.
 *
 * What it is NOT:
 *
 * - **Not a second writer.** Its buttons call the same `onDeclare` / `onProve`
 *   this screen's own controls call, so `DeclareView` and `ProveView` stay the
 *   only things that write, and the client's refetch-at-turn-end stays the
 *   single source of the offer. Nothing auto-banks; the press survives, it
 *   moved.
 * - **Not a second form.** The link and the attachment are the SAME state the
 *   Today form holds, so the two renderings cannot come to hold different
 *   evidence for one evening. The draft itself is text here, exactly as it is
 *   text on the card: editing it is what Today's box is for.
 * - **Not part of the message it sits beside.** It renders from the live offer,
 *   at a position — see lib/inline-offer, which is where that rule is made
 *   structural, and #219 is why it has to be.
 *
 * A control, only a control. Masterji's own words above it carry the
 * explanation — the card rides beside them, never instead of them.
 */
function CommitCard({
  offer,
  metricName,
  busy,
  uploadsEnabled,
  url,
  setUrl,
  image,
  setImage,
  onCommit,
}: {
  offer: LiveOffer;
  /** The one number they watch, or null when they have not named one — the
   * same gate the evening form's box is behind. "Today's <name>" is the only
   * thing that says what the figure is a count of. */
  metricName: string | null;
  busy: boolean;
  uploadsEnabled: boolean;
  url: string;
  setUrl: (next: string) => void;
  image: File | null;
  setImage: (next: File | null) => void;
  onCommit: () => void;
}) {
  if (offer.kind === "declare") {
    return (
      <div className={styles.inlineCommit}>
        <p className={styles.proofOfferLabel}>Today&apos;s task</p>
        <p className={styles.proofOfferText}>{offer.text}</p>
        <button className={styles.primaryBtn} disabled={busy} onClick={onCommit}>
          Declare it
        </button>
      </div>
    );
  }
  const owed = offer.missing ? missingPieces(offer.missing) : [];
  return (
    <div className={styles.inlineCommit}>
      {/* Shorter than the Today card's labels, and deliberately not a
          near-copy of them. At ≥821px both are on screen at once, and two
          blocks headed by strings that differ in one word read as a rendering
          bug rather than as one draft shown twice. Where each one sits already
          says which conversation it came out of; the label's job here is only
          to name the state, and the button below is what tells them apart —
          Today's fills a box, this one files. */}
      <p className={styles.proofOfferLabel}>
        {offer.missing ? "What Masterji has so far" : "Tonight's proof"}
      </p>
      <p className={styles.proofOfferText}>{offer.text}</p>
      {/* Shown on an incomplete draft rather than hiding the card, because an
          incomplete draft is filed on its merits today and that does not
          change. What must never happen is offering the press without the gap
          beside it — that is a builder pushed back for a piece nobody told
          them was missing. */}
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
      {metricName !== null && offer.metric !== null && (
        <p className={styles.proofOfferMetric}>
          Today&apos;s {metricName}: <strong>{offer.metric}</strong>
        </p>
      )}
      <input
        className={styles.input}
        placeholder="Link (optional)"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      {uploadsEnabled && (
        <label className={styles.attach}>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(e) => setImage(e.target.files?.[0] ?? null)}
          />
          <span>{image ? `📎 ${image.name}` : "📎 Attach a screenshot"}</span>
        </label>
      )}
      <button className={styles.primaryBtn} disabled={busy} onClick={onCommit}>
        {busy && image ? "Masterji is looking…" : "Submit proof"}
      </button>
    </div>
  );
}

/* --- drafts that survive the tab ------------------------------------------ */

/** Keeps one box's contents across a tab the phone decided to discard.
 *
 * Phone-first means Android reclaims background tabs constantly, and an
 * evening's proof is a paragraph of real thinking typed on a phone keyboard: a
 * WhatsApp notification mid-sentence costs the whole thing today, and "retype
 * it" at ten at night is how an honest day silently becomes a missed one.
 *
 * Mirrors the value rather than hooking the submit paths, which is what makes
 * it behaviour-neutral: every setter is covered, including the ones that are
 * not typing at all (Masterji's own proof draft filling the evening box, an
 * opener chip filling the composer), and clearing is not a code path of its own
 * — the same `setPmText("")` that empties the box on a settled verdict empties
 * the store, because the mirror follows the box wherever it goes.
 *
 * `key` is null when there is nothing to file the draft under yet — before the
 * first state payload lands, or the evening box before a task exists. Nothing
 * is read or written then.
 */
function usePersistedDraft(
  key: string | null,
  value: string,
  setValue: (next: (current: string) => string) => void
) {
  // Which key this box has already been restored for. Same job as seededFrom
  // below: restore once, so a refetch never refills a box the builder
  // deliberately cleared.
  const restored = useRef<string | null>(null);
  // The same fact as `restored`, in a form a render can read. A ref cannot be
  // one: the caller has to be re-rendered to say anything about what came
  // back, and writing to a ref does not do that. Keyed rather than boolean so
  // it answers for the box on screen — tomorrow's evening is a new key and has
  // restored nothing.
  const [restoredKey, setRestoredKey] = useState<string | null>(null);

  useEffect(() => {
    if (key === null) return;
    if (restored.current !== key) {
      restored.current = key;
      const saved = readDraft(key);
      // Only into an empty box, the same precedence the UNJUDGED re-seed uses:
      // anything already typed is newer than anything on disk. Returning here
      // also keeps this pass from writing — on it the box is still empty, and a
      // write would delete the draft this line is putting back.
      if (saved) {
        setValue((current) => current || saved);
        // Claimed only when the box was empty to receive it. This flag draws
        // "Your words came back — if you had a screenshot picked, pick it
        // again", which on a box that already had words is false twice over.
        // Nothing reaches that today: all four boxes start "" and the only
        // things that fill one — the UNJUDGED re-seed below, a drafted proof —
        // are declared after this hook, so they run after it and this pass
        // always sees an empty box. That ordering is what makes the line above
        // safe, it is one reordered hook away from not being true, and nothing
        // else states it.
        if (!value) setRestoredKey(key);
      }
      return;
    }
    writeDraft(key, value);
  }, [key, value, setValue]);

  return restoredKey !== null && restoredKey === key;
}

export default function Dashboard({
  user,
  state,
  goal,
  busy,
  error,
  setError,
  run,
  refresh,
  setState,
  pane,
  setPane,
  room,
  onSetTone,
  onRetired,
}: {
  user: SessionUser;
  state: CoachState;
  /** Narrowed out of `state` by the parent's branch, so nothing in here has to
   * ask again whether there is a goal — this component does not exist without
   * one. */
  goal: Goal;
  busy: boolean;
  error: string;
  /** The banner is the parent's, because `run` writes it on every mutation.
   * The chat needs it too: a turn that broke part of the way through is
   * reported here rather than in the transcript — see onError in `send`. */
  setError: (message: string) => void;
  run: (fn: () => Promise<void>) => Promise<void>;
  refresh: () => Promise<CoachState | null>;
  setState: Dispatch<SetStateAction<CoachState | null>>;
  /** Phone only: the dashboard and the chat take turns instead of stacking.
   * Held by the parent because the room's composer is measured against it too,
   * and the room lives up there. */
  pane: "today" | "chat";
  setPane: (next: "today" | "chat") => void;
  room: RoomProps;
  onSetTone: (next: CoachState["tone"]) => void;
  /** Hand the closing up to the parent: the screen that shows it is
   * <Onboarding />, which this render is about to be replaced by. */
  onRetired: (retirement: Retirement, pivotFrom: number | null) => void;
}) {
  const { gate, streak, today, checkins, transitions, messages, phases, guidance } =
    state;
  const { ws } = room;

  // chat
  // Masterji is reading this morning's task. Not part of `busy`: the form
  // stays fully usable while it runs.
  const [judging, setJudging] = useState(false);
  const declaring = useRef(false);
  const [draft, setDraft] = useState("");
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [pendingUserMsg, setPendingUserMsg] = useState<string | null>(null);
  // Where in the transcript the commit card is drawn, and which draft it was
  // drawn against. A place and a day, with no draft in it — see
  // lib/inline-offer for why that is the whole safety property, and #219 for
  // what it is protecting against.
  const [offerAnchor, setOfferAnchor] = useState<OfferAnchor | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  // The box you talk back in, so it can be measured against what's in it.
  const composerRef = useRef<HTMLTextAreaElement>(null);

  // forms
  // Rewording the goal. Offered only while the server says nothing is banked
  // against the current wording (goal.titleLocked), so the control is never on
  // screen in a state where pressing it would be refused.
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleText, setTitleText] = useState("");
  const [amText, setAmText] = useState("");
  // The hour named alongside this morning's task, as the select's own string
  // ("" is "didn't name one"). Not persisted like amText is: a draft exists so
  // half-typed words survive a closed tab, and there is no half-made choice
  // here to lose.
  const [amHour, setAmHour] = useState("");
  // The morning's box, so the drafted task can put the caret in it — same job
  // pmBoxRef does one screen later.
  const amBoxRef = useRef<HTMLTextAreaElement>(null);
  // Rewording the task already on the hook. An EDIT of today's open cycle, not
  // a second one: DeclareView updates the cycle still owing its proof, and this
  // control only renders on a card that has one. `declaringAgain` below is the
  // other thing and stays the other thing — that opens a new cycle after
  // tonight's proof has landed, which is a day with two pieces of real work in
  // it rather than a change of mind about the first.
  const [rewording, setRewording] = useState(false);
  const [pmText, setPmText] = useState("");
  const [pmUrl, setPmUrl] = useState("");
  const [pmImage, setPmImage] = useState<File | null>(null);
  // The evening's box, so the button that fills it can put the caret in it.
  const pmBoxRef = useRef<HTMLTextAreaElement>(null);
  // Which check-in the evening's box has already been filled from, so the
  // effect below seeds once rather than on every refetch.
  const seededFrom = useRef<number | null>(null);
  // The gate's last answer, and the situation it answered. Rendered only
  // while the two still match — see gateKey in lib/gate.
  const [gateNote, setGateNote] = useState<{ text: string; key: string } | null>(
    null
  );
  // What the phase that was just cleared had banked, said on the empty bar of
  // the phase it bought — and keyed exactly like gateNote, so it lasts as long
  // as the situation it describes and no longer.
  //
  // The moment it exists for: pressing "Open BUILD" turns a full marigold bar
  // and "Earned. BUILD is yours to open." into `0/2 proofs toward LAUNCH` over
  // an empty one, with the advance button back. Three real conversations
  // become a new debt, and nothing on the screen says the three are still on
  // the record. They are — gates.accepted_proofs counted them, the record card
  // still lists them, the retirement snapshot will count them again. The card
  // just stopped mentioning it at the moment it mattered most. This is the same
  // courtesy `· N more banked` already pays for surplus work, across a
  // transition instead of within a phase.
  //
  // The number is the server's, captured from the gate for the phase being left
  // BEFORE the refresh replaces it — not counted here over `checkins`, which is
  // a capped payload and would quietly go short on a goal past ninety days.
  //
  // It does not survive a reload, and that is the right lifetime rather than a
  // limitation: it answers the bar resetting under the builder's own press. A
  // builder arriving tomorrow to a 0/2 is not in that moment, and the record
  // card below is where the proofs themselves live.
  const [carried, setCarried] = useState<{ text: string; key: string } | null>(
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
  // Whether the record is showing everything or just the last week of it.
  // Deliberately not remembered between visits: the reason to open it is a
  // question you have today, and a builder who answered one last Tuesday
  // shouldn't be met by a wall of rows every morning after.
  const [showAllDays, setShowAllDays] = useState(false);
  // The days beyond the ones the dashboard payload carries. StateView caps at
  // CHECKIN_HISTORY, so on a goal past the cap "show all" has to go and get the
  // rest — the record used to offer all ninety of ninety-five and the other five
  // were simply gone.
  //
  // Both are stamped with the goal they belong to rather than cleared by an
  // effect. That was written against a render that never unmounted: retiring an
  // idea and starting the next one replaced `checkins` in place, and rows held
  // here without a name on them would have gone on rendering the dead goal's
  // record under the new goal's title. This screen dies with its goal now, so
  // the stamp is a second line of defence — kept because `days` and the
  // "couldn't load the earlier days" line both decide what to show by comparing
  // it, and a set of rows that cannot say which goal it came from is one
  // refactor away from being the wrong record again.
  const [allDays, setAllDays] = useState<{ goalId: number; rows: CheckIn[] } | null>(
    null
  );
  const [allDaysFailedFor, setAllDaysFailedFor] = useState<number | null>(null);
  // A builder who reached for tonight's box before tonight — finished early,
  // or filing at four because they're out at seven. Only ever forces the
  // evening half OPEN; everything that opens it on its own is in eveningOpen.
  const [filingNow, setFilingNow] = useState(false);
  // Retiring the current goal: the form, and what Masterji said about it.
  const [retiring, setRetiring] = useState(false);
  // The retire box itself, and a tick that counts the times Masterji opened it
  // rather than the builder pressing the link. Only the proposed ones scroll:
  // somebody who clicked "close this goal" is already looking at the control,
  // and a page that jumps under a press they just made is answering a question
  // they did not ask. A counter rather than a boolean so a second proposal in
  // the same conversation moves the page again.
  const retireBoxRef = useRef<HTMLDivElement>(null);
  const [closeProposedAt, setCloseProposedAt] = useState(0);
  // The one line about the phase you are in, and whether its box is open. The
  // box shows itself when the line is empty, which is the state every phase
  // starts in — nothing here nags, and ignoring it is a complete answer.
  const [intentDraft, setIntentDraft] = useState("");
  const [namingPhase, setNamingPhase] = useState(false);
  // The launch date and the room it goes into, and whether the box is open.
  // Both empty by default and never prefilled with a guess: a date the app
  // picked is not a commitment anybody made.
  const [launchDraft, setLaunchDraft] = useState("");
  const [pondDraft, setPondDraft] = useState("");
  const [namingLaunch, setNamingLaunch] = useState(false);
  // The one number they watch, and whether the box naming it is open. Same rule
  // as the launch date and for the same reason: no default and no placeholder,
  // because a metric the app chose is not one anybody decided to watch.
  const [metricDraft, setMetricDraft] = useState("");
  const [namingMetric, setNamingMetric] = useState(false);
  // Tonight's reading of it, as a string, because that is what an input holds
  // and "" has to stay distinguishable from 0 all the way to the wire — the
  // evening the number did not move is the one worth recording.
  const [pmMetric, setPmMetric] = useState("");
  // Whether the room beside the retire box is showing. Client-side only: the
  // room itself is a server row that exists once the builder has said
  // something in it, and this is just which of the two doors is open.
  const [reopening, setReopening] = useState(false);
  const [retireReason, setRetireReason] = useState("");

  // A closed idea being read back — available while a new goal is running.
  const [viewClosed, setViewClosed] = useState<Retirement | null>(null);

  // What each box's draft is filed under. Not one key shape for all of them,
  // because the three boxes stop being worth restoring at different moments:
  //
  //   the morning's task  — a day. There is no check-in to hang it on yet; the
  //                         row is created BY declaring, and this is the box
  //                         that declares. Tomorrow is a different task.
  //   the evening's proof — the check-in it is evidence for. The date would be
  //                         wrong twice over: a second cycle on one day is a
  //                         different task under the same date, and a proof
  //                         filed at 00:30 belongs to the day before it.
  //   the chat            — the goal. A half-typed sentence to Masterji is
  //                         about the idea, not about a day; the age rule in
  //                         readDraft is what keeps it from outliving its
  //                         moment.
  //
  // The goal half of that is structural now rather than a null check: this
  // component only exists under one. The evening's key is still null until
  // there is a task to be evidence for.
  const todayId = today?.id ?? null;
  const amKey = `${goal.id}.am.${localDate()}`;
  const pmKey = todayId === null ? null : `${goal.id}.pm.${todayId}`;
  const chatKey = `${goal.id}.chat`;
  usePersistedDraft(amKey, amText, setAmText);
  const pmRestored = usePersistedDraft(pmKey, pmText, setPmText);
  // The link belongs to the same form and is cleared on the same line as the
  // text. Restoring one without the other is worse than restoring neither: the
  // builder reads the box they left, presses Submit, and files a proof whose
  // link quietly went missing.
  usePersistedDraft(
    pmKey === null ? null : `${pmKey}.url`,
    pmUrl,
    setPmUrl
  );
  usePersistedDraft(chatKey, draft, setDraft);
  // An unread proof puts its own words back in the box, so the only thing the
  // card asks for — the same proof, once the model is answering — costs one
  // press.
  //
  // Runs after the restore above, and both only ever fill an EMPTY box, so a
  // draft the builder was still editing when the tab died wins over the copy
  // the server holds — which is the older of the two by definition.
  //
  // onProve already keeps them there for a builder still on the page. This is
  // the one who closed the tab and came back: their text is on the server and
  // nowhere else, and an empty box under "I couldn't read it, send it again"
  // is a retype charged for our outage. Seeded once per check-in, tracked by
  // id, so it never refills over somebody who cleared it to write a better one.
  const unread = today?.proofStatus === "UNJUDGED" ? today : null;
  useEffect(() => {
    if (!unread || seededFrom.current === unread.id) return;
    seededFrom.current = unread.id;
    setPmText((current) => current || unread.pmProofText);
  }, [unread]);

  // Pin the log to the newest turn by scrolling the log itself.
  // scrollIntoView walks up to the nearest scrollable ancestor, and on a
  // phone — where the log only becomes its own scroll box once the chat
  // pane is showing — that ancestor is the page: every load dropped the
  // builder at the very bottom of it, below the whole dashboard.
  //
  // Which end of the newest turn gets pinned is lib/log-pin.ts, and the
  // arithmetic lives there because it is the same question for both logs.
  useEffect(() => {
    pinLog(messagesRef.current, streamingText !== null);
  }, [messages.length, streamingText, pane]);

  // Put a proposed close on screen. An effect rather than a line in the handler
  // because the box has to exist before anything can scroll to it, and this
  // fires on the commit that opened it.
  //
  // Waits for the turn to end. The proposal arrives as a tool call MID-STREAM,
  // and the two pins above run on every `streamingText` change — once per token
  // — so scrolling from the handler would be moving the card under a sentence
  // still being written. Gating on `streamingText === null` puts this on the
  // commit where the turn settles instead, which is also when the reply that
  // says the box is open has finished saying it.
  //
  // No `behavior: "smooth"`, and not as an oversight: it is a silent no-op in
  // at least one Chromium build that scrolls `instant` on the same element
  // perfectly (measured — 0px moved, twice, with reduced-motion off), and a
  // scroll that sometimes does nothing is worse than one that does not animate.
  // `pinLog` above sets `scrollTop` outright for the same reason.
  //
  // Not scrollIntoView's usual hazard here either: the nearest scrollable
  // ancestor is `.side`, the column the goal card lives in, so this moves that
  // column and leaves the page alone. On a phone the card sits in a
  // display:none pane whenever the chat is showing, where it is a harmless
  // no-op — the builder is reading the reply that says the box is open, and it
  // is open when they cross over. Which is why the pane is not switched for
  // them: they asked to get out, not to be moved off the answer.
  useEffect(() => {
    if (!closeProposedAt || streamingText !== null) return;
    retireBoxRef.current?.scrollIntoView({ block: "center" });
  }, [closeProposedAt, streamingText]);

  // This screen's composer. The room's is fitted by useRoom, with the same
  // function out of lib/fit-box — one arithmetic, two boxes, and neither
  // component reaching into the other's refs to do it.
  const fitComposer = useCallback(() => {
    fitBox(composerRef.current, messagesRef.current);
  }, []);

  // Fit the box when it attaches, not only when the draft changes. `draft`
  // arrives from storage in an effect after this element exists (see
  // usePersistedDraft), so a builder whose tab was discarded mid-sentence
  // comes back to five lines in a box `rows` gave one row to. The draft effect
  // below covers that too; this covers the mount itself, which is the case
  // nothing else would re-run for.
  //
  // It used to carry a second job — the chat section unmounted with the goal
  // while `draft` outlived it in the parent. It does not outlive it any more:
  // the draft is declared here and dies with this screen, which is the point
  // of the split. A half-typed line about a goal that has since been retired
  // is not a line anybody wants back under the next one.
  const attachComposer = useCallback((el: HTMLTextAreaElement | null) => {
    composerRef.current = el;
    if (el) fitBox(el, messagesRef.current);
  }, []);

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

  // Focus, on the same terms Escape is on: the drill-in holds it while it is
  // the top panel and hands it over while a day is open above it. Unlike
  // Escape, standing down is not the same as closing — the row a day was
  // opened from is inside THIS panel, and that is where DayDetail gives focus
  // back to.
  const phaseDialog = useRef<HTMLDivElement>(null);
  useDialogFocus(phaseDialog, Boolean(viewPhase), !viewDay);

  // Put them in the box the button just revealed — the same move the draft
  // button and the goal examples make, and for the same reason: a press that
  // ends in a hunt for the caret is a press that half worked. In an effect
  // rather than in the handler because this box does not exist at the moment
  // of the press; the render that creates it is what focus has to wait for.
  useEffect(() => {
    if (filingNow) pmBoxRef.current?.focus();
  }, [filingNow]);

  // The same move for the morning's box, which the reword control reveals the
  // same way. Separate effect rather than one with both flags in it: they open
  // two different boxes, and a shared dependency list would move the caret into
  // the evening's whenever the morning's opened.
  useEffect(() => {
    if (rewording) amBoxRef.current?.focus();
  }, [rewording]);

  const onRenameGoal = () =>
    run(async () => {
      const next = titleText.trim();
      // Nothing to say and nothing to write: closing the box IS the answer to
      // an empty edit or the same words back, and a round-trip for either would
      // put "Reworded: X → X" through a server that then declines to log it.
      if (!next || next === goal.title) {
        setEditingTitle(false);
        return;
      }
      await updateGoalTitle(goal.id, next);
      setEditingTitle(false);
      await refresh();
    });

  /** Declare today's task.
   *
   * `text` is for the surface that holds its own copy of the draft — the
   * inline commit card in the log, which has no box of its own and presses the
   * words it is showing. Absent, this reads the morning's box, which is every
   * other caller. One handler either way: the inline card is an additional
   * surface for the same press, never a second path to DeclareView.
   *
   * Every call site passes its own arguments rather than being handed to
   * `onClick` bare — a React MouseEvent arriving as `text` would be a truthy
   * object, and `.trim()` on it would throw at the one moment a builder is
   * trying to declare.
   */
  const onDeclare = (text?: string) =>
    run(async () => {
      // `disabled={busy}` can't guard this alone — setBusy is async, so two
      // clicks in one tick both get through. The DB constraint keeps that
      // idempotent, but declaring also CLEARS the judgement fields, so a
      // second write landing after the judge response would erase Masterji's
      // read of the task. A ref flips synchronously; state doesn't.
      const task = (text ?? amText).trim();
      if (!task || declaring.current) return;
      declaring.current = true;
      try {
        // The hour comes from the select either way: naming one is an optional
        // tap on the Today card, and the log is not where that choice lives.
        // An inline declaration with no hour named is a promise about the task
        // and not about the clock, which is the ordinary case anyway.
        const checkin = await declare(
          task,
          amHour === "" ? null : Number(amHour)
        );
        setAmText("");
        setAmHour("");
        setDeclaringAgain(false);
        // The reword box shuts on the write that answers it. Left open it
        // would sit over the freshly declared task holding the words the
        // builder just sent, which reads as a press that did nothing.
        setRewording(false);
        // A second cycle starts at its own morning. Without this, declaring
        // again after an early filing would drop the builder straight back
        // onto the evening form for a task thirty seconds old.
        setFilingNow(false);
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

  /** File tonight's proof. `text` and `metric` are the inline commit card's,
   * on the same terms `onDeclare` states — the card presses the draft it is
   * showing, and the link and the screenshot are the same state this form
   * holds, so there is one set of evidence for one evening whichever surface
   * files it. */
  const onProve = (text?: string, metric?: number | null) =>
    run(async () => {
      const proof = (text ?? pmText).trim();
      if (!proof) return;
      const filed = await prove(
        proof,
        pmUrl.trim(),
        pmImage,
        // "" is no reading, "0" is a reading of zero. Number("") is 0, so the
        // emptiness has to be checked before the conversion rather than after.
        metric === undefined
          ? pmMetric.trim() === ""
            ? null
            : Number(pmMetric.trim())
          : metric
      );
      // Emptying the box is right when the evening is settled — accepted, or
      // pushed back and owed a different answer. An unread proof is neither:
      // nothing was wrong with it, the model just wasn't there, and the only
      // thing being asked for is the same words again. Clearing them would
      // make our outage look like their retype.
      if (filed.checkin.proofStatus !== "UNJUDGED") {
        setPmText("");
        setPmUrl("");
        setPmImage(null);
        // Cleared on the same line as the rest of the form, and only when the
        // evening is settled: a pushed-back proof gets refiled from this box, and
        // the number is a fact about the day that the push-back did not change.
        setPmMetric("");
      }
      await refresh();
    });

  const onNameMetric = () =>
    run(async () => {
      if (!metricDraft.trim()) return;
      await setMetric(goal.id, metricDraft.trim());
      setNamingMetric(false);
      await refresh();
    });

  const onAdvance = () =>
    run(async () => {
      setGateNote(null);
      setCarried(null);
      // The phase being left and what it had banked, read off the state that is
      // about to be replaced. Both are the server's numbers for the phase they
      // describe, which is what makes them still true after the refresh.
      const leaving = goal.phase;
      const banked = state.gate?.banked ?? 0;
      let detail: string;
      try {
        detail = (await advanceGoal(goal.id)).detail;
      } catch (e) {
        // 409 = the gate said no; its message IS the feature.
        if (e instanceof ApiError && e.status === 409) detail = e.message;
        else throw e;
      }
      // Stamped with the state AFTER the answer, not before it: an advance
      // moves the phase and a refusal doesn't, so this is the only stamp that
      // makes the note last exactly as long as what it describes.
      const after = await refresh();
      const key = gateKey(after);
      setGateNote({ text: detail, key });
      // Only when the phase actually moved. A refusal leaves the bar exactly
      // where it was, and telling a builder their proofs are still on the
      // record while they are looking at the meter that still counts them
      // would be an answer to a question nobody asked.
      if (banked > 0 && after?.goal && after.goal.phase !== leaving) {
        setCarried({
          text: `${banked} proof${banked === 1 ? "" : "s"} from ${leaving} ${
            banked === 1 ? "stays" : "stay"
          } on the record.`,
          key,
        });
      }
    });

  /** Close the goal. `pivot` changes nothing about the closing — same
   * ABANDONED row, same computed verdict — and only remembers which goal the
   * next one came out of, for the screen that is about to ask for it. */
  const onRetire = (
    outcome: "ABANDONED" | "COMPLETED",
    opts: { pivot?: boolean } = {}
  ) =>
    run(async () => {
      if (!retireReason.trim()) return;
      const closing = goal.id;
      const { retirement } = await retireGoal(
        closing,
        retireReason.trim(),
        outcome
      );
      setRetireReason("");
      setRetiring(false);
      // Hold Masterji's reaction on screen, and the pivot with it. Both are
      // handed UP: the refresh below takes the goal away, the parent branches
      // to <Onboarding />, and this component is gone by the time either is
      // read. Without them that screen would be an empty "One goal." form the
      // instant the goal closed — the worst possible moment to be handed a
      // blank input.
      onRetired(retirement, opts.pivot ? closing : null);
      await refresh();
    });
  /** Name what the phase you are standing in will produce. One line, and
   * nothing depends on it: the phase advances on proofs whether this is set,
   * changed or ignored. Re-fetches rather than patching state by hand, because
   * the line goes into the next system prompt and the transcript on screen is
   * about to be read by a coach that has it. */
  const onNamePhase = () =>
    run(async () => {
      const text = intentDraft.trim();
      if (!text) return;
      await setPhaseIntent(goal.id, text);
      setNamingPhase(false);
      setIntentDraft("");
      await refresh();
    });

  /** Name the day it goes in front of people. Append-only server-side: this
   * never edits the last answer, it writes another row, so moving the date
   * leaves the move on the record. Nothing about it can refuse anything. */
  const onNameLaunch = () =>
    run(async () => {
      if (!launchDraft || !pondDraft) return;
      await setLaunchDate(goal.id, launchDraft, pondDraft);
      setNamingLaunch(false);
      await refresh();
    });
  // Persisted on the user, not held in this component: a builder who asked to
  // think out loud on their phone should still be in that mode on their laptop.
  //
  // Sets a named mode rather than flipping the current one: the control is two
  // options with one lit, so "the mode I clicked" is the only thing a click can
  // mean. Re-picking the mode already running is a no-op, not a round-trip.
  const onSetMode = (next: CoachState["mode"]) =>
    run(async () => {
      if (state.mode === next) return;
      await updatePrefs({ mode: next });
      setState((s) => (s ? { ...s, mode: next } : s));
    });

  /** Say something to Masterji. `retryOf` is the words of a turn the model
   * dropped, sent again from the notice that reported it — so the composer is
   * not the only way a message can be sent, and a builder whose turn died gets
   * to answer that where it happened rather than retyping a paragraph they
   * already wrote. Only the composer's own send clears the composer. */
  const send = async (retryOf?: string) => {
    const content = (retryOf ?? draft).trim();
    if (!content || streamingText !== null) return;
    if (retryOf === undefined) setDraft("");
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
        // Masterji asked for the close box, so open it. This is the whole of
        // what propose_goal_close does: nothing has closed, the goal is still
        // active, and it stays active until onRetire below POSTs a reason and
        // an exit the builder wrote and pressed. Unlike onGate this appends
        // nothing to the transcript — there is no server answer to report, and
        // his own words already say where he sent them.
        onCloseProposed: () => {
          setRetiring(true);
          setCloseProposedAt((n) => n + 1);
        },
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

  // What the record can render, and what the record actually holds. They differ
  // only past the payload cap, and the count in the button has to be the second
  // one or it is describing the truncation rather than the record.
  const days = allDays?.goalId === goal.id ? allDays.rows : checkins;
  const daysHeld = Math.max(state.checkinsTotal, checkins.length);
  const daysMissing = daysHeld > days.length;
  // Which cycle of its own day each row is. Computed once over the widest set
  // this render holds, because the record card, the phase drill-in and the day
  // panel all show subsets of it and must call the same row the same thing.
  // Not memoised, and now because it is not worth memoising rather than
  // because it cannot be: a `useMemo` is legal in this component, which is the
  // whole point of it being one. This is a Map over at most the rows already
  // being mapped, filtered and searched inline on this same render, so a memo
  // would buy a dependency array and nothing else. The line worth keeping is
  // that the choice is now a choice.
  const cycles = cycleOrdinals(days);
  const cycleOf = (c: CheckIn) => cycles.get(c.id) ?? 1;
  const doneIdx = phases.indexOf(goal.phase);
  // Read twice below — once by the meter's colour and once by the branch that
  // decides what the card says. One function so they cannot fork; see lib/gate.
  const earned = isEarned(gate);
  // The row that opened the phase they are standing in, which is where the one
  // line about it lives. Null in IDEA — nothing unlocked it, so there was never
  // a moment at which to ask — and that is the whole of the "no ask on the
  // first phase" rule, said once here rather than branched on below.
  const phaseIntent =
    transitions.filter((t) => t.toPhase === goal.phase).slice(-1)[0] ?? null;
  // What today's loop is doing. Five rules, all in lib/day.ts and pinned there
  // — they used to be these expressions, in the one file no test can reach.
  const dayOpen = isDayOpen(today);
  const draftWaiting = isDraftWaiting(today);
  const notesRunning = isNotesRunning(today);
  const owed = today?.proofMissing ? missingPieces(today.proofMissing) : [];
  // The clock is read HERE, at render, rather than inside the rule: a card left
  // open on a desk since morning has caught up by the time anyone looks at it
  // again, and a rule that fetched its own hour would be untestable on both
  // sides of EVENING_FROM.
  const eveningOpen = isEveningOpen(today, new Date().getHours(), filingNow);

  // The draft the Today card is showing with its fill control, read off the
  // same state that card branches on — so the conversation and the card cannot
  // disagree about whether a control exists.
  const offer = liveOffer({ declarationOffer: state.declarationOffer, today });
  const offerKey = offer?.key ?? null;
  const newestMessageId = messages.length ? messages[messages.length - 1].id : null;
  // The date is read here, at render, for the reason the hour above it is:
  // this decides whether a tab left open since yesterday may still press a
  // draft into today's row, and a rule that fetched its own date would be
  // untestable on both sides of midnight.
  const localToday = localDate();
  // Lay the anchor down when a new draft arrives, and only then. Same key on a
  // later turn returns the identical object, so React bails out of the set and
  // the card keeps its place in the transcript rather than following the
  // conversation down.
  useEffect(() => {
    setOfferAnchor((cur) => nextAnchor(cur, offerKey, newestMessageId, localToday));
  }, [offerKey, newestMessageId, localToday]);
  // And the anchor a card may actually be drawn against. Null is a card that is
  // not there, never a disabled one: a greyed-out `Declare it` in last
  // Tuesday's scrollback is still an offer of a door.
  const cardAt = cardIndex(liveAnchor(offerAnchor, offerKey, localToday), messages.map((m) => m.id));
  /** The press, built here because only this screen knows what the other
   * boxes hold. The card supplies the words; everything else is the same
   * state, and the same handler, as the Today form's own controls. */
  const onCommit = () => {
    if (!offer) return;
    if (offer.kind === "declare") {
      onDeclare(offer.text);
      return;
    }
    // A reading the builder typed beats the one Masterji heard, which is the
    // precedence every restore in this file already uses: what is in the box
    // is newer than what came with the draft. Nothing at all when no metric is
    // named — the server offers no reading until one is, and a number with no
    // noun beside it is the app inventing the metric.
    onProve(
      offer.text,
      state.metric === null
        ? null
        : pmMetric.trim() !== ""
          ? Number(pmMetric.trim())
          : offer.metric
    );
  };

  /** One row of the log. Lifted out of the map it used to be written inside so
   * the map can put something beside a turn without the two getting tangled —
   * see the fragment below. Not a component: it closes over `send` and the
   * transcript, and a component would need both as props for no gain. */
  const renderTurn = (m: CoachState["messages"][number], i: number) => {
    // A turn the model dropped before its first word. It is in the
    // log because the refetch that ends every turn would otherwise
    // erase the bubble the builder was watching — but it is the app
    // reporting a failure, not Masterji saying something, and drawn
    // as a bubble with his avatar that is exactly what it became: a
    // sentence attributable to him, sitting in the record a week
    // later next to real coaching. So: no avatar, no bubble, and the
    // way out of it right there, because the thing a builder wants
    // at that moment is the turn they already typed, not the job of
    // typing it again.
    // The week read back — the second thing a SYSTEM row can be. It
    // gets a block rather than the notice's pill below: that pill is
    // a centred oval sized for one short line, and this is three or
    // four. No retry either, and that is the point of telling them
    // apart — this arrives on a Monday with an unrelated conversation
    // above it, so a button built from "the last thing they said"
    // would offer to send a sentence from last week.
    if (m.role === "SYSTEM" && m.kind === "DIGEST") {
      return (
        <div data-turn className={styles.digestMsg}>
          <p className={styles.systemText}>{m.content}</p>
        </div>
      );
    }
    if (m.role === "SYSTEM") {
      const said = saidBefore(messages, i);
      return (
        <div data-turn className={styles.systemMsg}>
          <p className={styles.systemText}>{m.content}</p>
          {said && (
            <button
              className={styles.retryBtn}
              // Same guard the composer's Send has: one turn in
              // flight at a time, whichever button started it.
              disabled={streamingText !== null}
              onClick={() => send(said)}
            >
              Send it again
            </button>
          )}
        </div>
      );
    }
    return (
      <div
        data-turn
        className={m.role === "COACH" ? styles.coachMsg : styles.userMsg}
      >
        {m.role === "COACH" && <span className={styles.avatar}>म</span>}
        <p className={styles.msgBody}>{m.content}</p>
      </div>
    );
  };

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
        {/* Outside .headerRight, and that placement is the fix rather than an
            accident of refactoring.

            At 360px the four controls needed 322px of a 320px content box, so
            "sign out" wrapped onto a third header line: 150px of header on the
            smallest screen this runs on, against a chat pane that only had
            230px to spend. #179 had already fought the same deficit down from
            15px to 2px by tightening the gap, and stopped there correctly —
            the next 2px would have come out of the 44px touch targets it was
            buying, and this does not give those back.

            So the room comes from the row above instead. The wordmark is 146px
            of a 360px row and the rest of that row was doing nothing. Measured
            at 360×640 with the switch up here, the control row went from 320px
            of 320px — full, and overflowing onto a third line — to 239px, and
            the header from 150px to 106px. That 81px of slack is the point: a
            longer label, a wider Hindi string or a fifth control no longer puts
            it back on three lines, which is exactly what shaving the gap to 8px
            would not have survived.

            One DOM node, moved — not a second copy behind a breakpoint. Desktop
            is unchanged: `.header > .toneSwitch` takes `margin-left: auto`, so
            it sits against the control group where it always has.

            Both languages on screen with the live one lit, the same fix the
            mode switch got for the same reason. The no-goal screen renders this
            same control: the room before the goal speaks Hinglish too, and that
            was the only place to say so. */}
        <ToneSwitch tone={state.tone} busy={busy} onSet={onSetTone} />
        <div className={styles.headerRight}>
          {/* The mode used to sit here, next to the language toggle, on the
              grounds that both are "how Masterji talks to you". They aren't
              the same kind of setting. Language is picked once and forgotten;
              the mode is reached for mid-conversation, at the moment the
              replies stop fitting the problem — so it now lives over the
              composer, with the conversation it governs. This corner is
              account chrome, and nobody looks for a way of talking in it. */}
          {/* The streak and the lifetime count used to sit here, between the
              language switch and the username. They are on the goal card now,
              beside the days-in-phase line — see the comment there. What is
              left in this corner is account chrome, which is all this corner
              was ever supposed to be. */}
          <span className={styles.who}>{user.username}</span>
          <TourLink />
          <Changelog />
          <SignOutButton />
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
            {editingTitle ? (
              <div className={styles.renameBox}>
                <input
                  className={styles.input}
                  value={titleText}
                  autoFocus
                  maxLength={200}
                  onChange={(e) => setTitleText(e.target.value)}
                />
                <button
                  className={styles.secondaryBtn}
                  disabled={busy}
                  onClick={onRenameGoal}
                >
                  Save wording
                </button>
                <button
                  className={styles.linkBtn}
                  onClick={() => setEditingTitle(false)}
                >
                  leave it
                </button>
              </div>
            ) : (
              <div className={styles.goalHead}>
                <h2 className={styles.goalTitle}>{goal.title}</h2>
                {/* A control, not an explanation — what it costs and why it
                    stops being offered is the tour's job. Gone the moment the
                    first proof is banked, which is also when the server starts
                    refusing it. */}
                {!goal.titleLocked && (
                  <button
                    className={styles.linkBtn}
                    onClick={() => {
                      setTitleText(goal.title);
                      setEditingTitle(true);
                    }}
                  >
                    reword
                  </button>
                )}
              </div>
            )}

            {/* The sharper wording as Masterji heard them arrive at it in
                chat. Same bargain as the morning's task, the evening's proof
                and the launch day — he writes it down, they press it — and
                the press here is Save wording, through GoalUpdateView, the
                one endpoint that has ever renamed a goal.

                BELOW the title rather than above it, which is the opposite of
                where the other three sit, and deliberately. Those render above
                a form control because the label under them is the question and
                the draft is the answer. There is no question here: the line
                above is the goal, the card's job is to say where you stand,
                and a coach's alternative sitting over the sentence would be
                the app leading with somebody else's phrasing of the builder's
                idea. Under it, it is what it is — a suggestion about the line
                you just read.

                Outside the ternary, so it is on the card whether or not the
                box is open: the reword control is a text link, and a draft
                visible only after finding that link is a draft behind the hunt
                this whole direction exists to remove. Tapping it opens the box
                already holding the words — one control, both jobs.

                Not guarded on `titleLocked` here. The server stops serving the
                offer at the same count that hides the control and 409s the
                press, so this string is empty exactly when the control is
                gone. One lock, read in one place.

                "edit it before you save" rather than the other three's "edit
                it below": those sit above their control and this one does not,
                and the box the press opens takes the title's place ABOVE it.
                Driven at 360px, where the instruction pointed at the stepper.
                */}
            {goal.titleOffer && (
              <div className={styles.proofOffer}>
                <p className={styles.proofOfferLabel}>
                  Masterji heard a sharper version
                </p>
                <p className={styles.proofOfferText}>{goal.titleOffer}</p>
                <button
                  type="button"
                  className={styles.proofOfferBtn}
                  onClick={() => {
                    setTitleText(goal.titleOffer);
                    setEditingTitle(true);
                  }}
                >
                  Use this — edit it before you save
                </button>
              </div>
            )}

            {/* The idea under its own headline. Absent on every goal committed
                before the field existed, and on any goal still short of IDEA's
                proof — so it appears the evening the idea is cleared rather
                than sitting empty on the card asking to be filled in. */}
            {goal.brief && <p className={styles.goalBrief}>{goal.brief}</p>}

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
                  // The title is the sighted pointer's explanation and a phone
                  // never shows it; this is the same sentence for a screen
                  // reader, which would otherwise be read "IDEA, button" and
                  // left to guess. It also names the chip for the marker
                  // .stepDone::after draws — a bare glyph in the accessible
                  // name would be the affordance announcing itself as content.
                  aria-label={
                    i < doneIdx ? `See what happened in ${p}` : undefined
                  }
                >
                  {p}
                </li>
              ))}
            </ol>
            {/* Three facts of the same kind: how long this phase has been
                open, the run going, and the days behind the builder. They are
                all "how long has this been happening", they all move on the
                same clock, and they now sit in one row against the stepper
                they are facts about.

                The days-in-phase line came here first, and the argument it was
                given retires the other two. The header's right-hand group is
                pinned to fixed slots precisely so its controls hold still, and
                a badge whose width moves with the number in it would shift
                "What's new" and "sign out" under the thumb — worst on the
                morning a phase advances, which is the one morning nothing
                should move. At 375px that row was already documented as full,
                and with the badges in it the header ran to three rows and
                150px at 360px: 23% of the viewport, on every screen, growing
                with the streak. The account that had kept nothing got the
                compact header, and the one that had kept the promise for five
                weeks paid for it in chrome. Here the badges cost no control a
                position and the header is two rows for everyone.

                Every number is the server's. days-in-phase is the same
                subtraction the coach is handed in its state block, so a
                builder reading this and a coach answering them about it are
                quoting one measurement — it is never counted here.

                All three are hidden at zero, which is why the row can be empty
                and why it is not rendered when it is. On day one a phase has
                been open for no days, there is no run, and there is nothing
                behind the builder: three counters announcing they have nothing
                to count, on the first screen of the product.

                No threshold at which any of them changes appearance — see
                .phaseDays. */}
            {(state.daysInPhase > 0 ||
              streak > 0 ||
              state.bestStreak > 0 ||
              state.lifetimeDays > streak) && (
              <div className={styles.cardFacts}>
                {state.daysInPhase > 0 && (
                  <span className={styles.phaseDays}>
                    {state.daysInPhase} day{state.daysInPhase === 1 ? "" : "s"} in{" "}
                    {goal.phase}
                  </span>
                )}
                {/* A run that is going, and a run that was. The zero on its own
                    was the whole message after a missed day — and a bare zero
                    reads as "none of it happened" at exactly the moment
                    quitting looks reasonable. The best run is already on the
                    record; it just never reached the screen where it would do
                    some good. */}
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
                ) : null}
                {/* Survives retiring a goal — the streak is about this idea,
                    the lifetime count is about the builder. */}
                {state.lifetimeDays > streak && (
                  <span
                    className={styles.lifetime}
                    title="Days worked across every goal"
                  >
                    {state.lifetimeDays} total
                  </span>
                )}
              </div>
            )}
            <p className={styles.phaseHint}>{guidance?.phaseHint}</p>

            {/* And under the hint the server chose, the one that is theirs. The
                hint moves with the count on a phase with beats (guidance.BEATS
                — VALIDATION's three conversations each ask for something
                different) and is the phase's constant everywhere else, but
                either way it is a sentence written for every builder in that
                position. This is not: a phase has a bar and no shape, and
                "smallest thing a real user can touch this week" cannot tell the
                coach whether tonight's task is the thing THIS builder decided
                on the morning the phase opened.

                Never a gate, and the shape of the control says so — no ring, no
                counter, and it is skippable by ignoring it. gates.try_advance
                has never read PhaseTransition's contents and does not start.
                IDEA has no row (nothing unlocked it), so the ask is correctly
                absent on the phase everybody starts in. */}
            {phaseIntent !== null &&
              (phaseIntent.intent && !namingPhase ? (
                <button
                  type="button"
                  className={styles.phaseIntent}
                  onClick={() => {
                    setIntentDraft(phaseIntent.intent);
                    setNamingPhase(true);
                  }}
                  title="What you said this phase would produce — tap to reword"
                >
                  {phaseIntent.intent}
                </button>
              ) : (
                <div className={styles.phaseIntentBox}>
                  {/* The line as Masterji heard them say it, when they answered
                      the question in chat instead of here. Same bargain as the
                      morning's task and the evening's proof: he writes it
                      down, they press it — and it renders ABOVE the ask for
                      the same reason those two do, because this is the answer
                      and the label below is the question.

                      Nothing is named by any of this. The button fills the
                      input, and Save is still what posts it, through the one
                      endpoint that has ever written a phase line.

                      Inside the box branch, so a builder who has already
                      pressed a line keeps seeing the line they pressed rather
                      than an alternative to it — and a later draft is still
                      reachable, because tapping that line to reword opens this
                      same box with the newer offer above it. */}
                  {phaseIntent.intentOffer && (
                    <div className={styles.proofOffer}>
                      <p className={styles.proofOfferLabel}>
                        Masterji heard what this phase is for
                      </p>
                      <p className={styles.proofOfferText}>
                        {phaseIntent.intentOffer}
                      </p>
                      <button
                        type="button"
                        className={styles.proofOfferBtn}
                        onClick={() => setIntentDraft(phaseIntent.intentOffer)}
                      >
                        Use this — edit it below if it&apos;s not right
                      </button>
                    </div>
                  )}
                  <label
                    className={styles.phaseIntentLabel}
                    htmlFor="phase-intent"
                  >
                    What will {goal.phase} have produced?
                  </label>
                  <div className={styles.phaseIntentRow}>
                    <input
                      id="phase-intent"
                      className={styles.input}
                      placeholder="e.g. three hostellers who'd pay today"
                      value={intentDraft}
                      maxLength={280}
                      onChange={(e) => setIntentDraft(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && onNamePhase()}
                    />
                    <button
                      type="button"
                      className={styles.secondaryBtn}
                      disabled={busy || !intentDraft.trim()}
                      onClick={onNamePhase}
                    >
                      Save
                    </button>
                  </div>
                </div>
              ))}

            {/* The day they said they'd launch, under the gate meter it sits
                beside in kind: both are one number about where this goal is.
                The difference is who put it there — every other number on this
                card was earned or counted, and this one is the builder's own
                word, which is the whole of what makes it work.

                A control, and only a control. What a launch date is FOR — that
                BUILD dies from drift in week three, that the slip trail is the
                consequence and there is no other one — is a sentence in the
                tour, not help text wedged in here.

                Not before BUILD: a date on a goal with no artifact is a wish,
                and the server refuses it. */}
            {state.canSetLaunch && (
              <div className={styles.launch}>
                {state.launch && !namingLaunch ? (
                  <button
                    type="button"
                    className={styles.launchSet}
                    onClick={() => {
                      setLaunchDraft(state.launch!.date);
                      setPondDraft(state.launch!.pond);
                      setNamingLaunch(true);
                    }}
                  >
                    <span className={styles.launchWhen}>
                      Launch {formatDay(state.launch.date)} ·{" "}
                      {state.launch.daysOut === 0
                        ? "today"
                        : state.launch.daysOut > 0
                          ? `${state.launch.daysOut}d out`
                          : `${Math.abs(state.launch.daysOut)}d ago`}
                    </span>
                    {/* Stated, never softened. The trail is the mechanism, and
                        a move you can hide is not a commitment device. */}
                    {state.launch.moves > 0 && (
                      <span className={styles.launchMoved}>
                        moved {state.launch.moves}×
                      </span>
                    )}
                  </button>
                ) : (
                  <div className={styles.launchBox}>
                    {/* The day and the room as Masterji heard them agreed in
                        chat, when the date got talked down from "someday" to a
                        Friday there rather than here. Same bargain as the
                        morning's task and the evening's proof — he writes it
                        down, they press it — and above the ask for the same
                        reason those two are, because this is the answer and the
                        label below is the question.

                        Nothing is committed by any of this. The button fills
                        the two controls; Set is still what posts them, through
                        the one endpoint that has ever written a launch
                        commitment. That matters more here than anywhere: the
                        record is append-only and its slip trail is the whole
                        consequence, so a date on it that nobody pressed would
                        be a move the builder never made.

                        Inside the box branch, so a builder who has already set
                        a day keeps seeing the day they set rather than an
                        alternative to it — and a later draft is still
                        reachable, because tapping that day to move it opens
                        this same box with the newer offer above it. */}
                    {state.launchOffer && (
                      <div className={styles.proofOffer}>
                        <p className={styles.proofOfferLabel}>
                          Masterji heard the day and the room
                        </p>
                        <p className={styles.proofOfferText}>
                          {formatDay(state.launchOffer.date)} ·{" "}
                          {state.ponds.find(
                            (p) => p.value === state.launchOffer!.pond,
                          )?.label ?? state.launchOffer.pond}
                        </p>
                        <button
                          type="button"
                          className={styles.proofOfferBtn}
                          onClick={() => {
                            setLaunchDraft(state.launchOffer!.date);
                            setPondDraft(state.launchOffer!.pond);
                          }}
                        >
                          Use this — change it below if it&apos;s not right
                        </button>
                      </div>
                    )}
                    <label className={styles.launchLabel} htmlFor="launch-date">
                      When does it go in front of them?
                    </label>
                    <div className={styles.launchRow}>
                      <input
                        id="launch-date"
                        type="date"
                        className={styles.input}
                        value={launchDraft}
                        min={localDate()}
                        onChange={(e) => setLaunchDraft(e.target.value)}
                      />
                      {/* The ladder is launch-checklist.md's, served rather
                          than copied here — a builder inventing a fifth rung is
                          a builder avoiding the four. */}
                      <select
                        className={styles.input}
                        aria-label="Which room you'll launch into"
                        value={pondDraft}
                        onChange={(e) => setPondDraft(e.target.value)}
                      >
                        <option value="">Which room?</option>
                        {state.ponds.map((p) => (
                          <option key={p.value} value={p.value}>
                            {p.label}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        disabled={busy || !launchDraft || !pondDraft}
                        onClick={onNameLaunch}
                      >
                        Set
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* The one number, at the end of the ladder. Beside the launch date
                because they are the same kind of thing: the only two facts on
                this card the builder put there themselves rather than earned,
                and the only two nothing counts.

                A control, and only a control — same rule the launch date
                follows. Why you watch one number and not four, and that a number
                which falls costs nothing, is a sentence in the tour rather than
                help text wedged in here.

                TRACTION only, and offered on the phase rather than on arriving
                in it: TRACTION is the last rung, so a builder who was already
                standing here when this shipped has no advance left for an
                invitation to ride in on. */}
            {state.canSetMetric && (
              <div className={styles.launch}>
                {state.metric && !namingMetric ? (
                  <button
                    type="button"
                    className={styles.launchSet}
                    onClick={() => {
                      setMetricDraft(state.metric!.name);
                      setNamingMetric(true);
                    }}
                  >
                    <span className={styles.launchWhen}>
                      Watching {state.metric.name}
                      {/* The series, newest last, so it reads the way it moved.
                          Absent until there is a reading — a metric named this
                          morning has no line yet, and drawing an empty one would
                          be the app filling in the builder's answer. */}
                      {state.metric.series.length > 0 && (
                        <>
                          {" · "}
                          {state.metric.series
                            .slice(-METRIC_PREVIEW)
                            .map((r) => r.value)
                            .join(" → ")}
                        </>
                      )}
                    </span>
                    {/* Stated, never softened — the same rule the launch date's
                        move count follows. A swap you can hide is not a record of
                        what you were watching. */}
                    {state.metric.swaps > 0 && (
                      <span className={styles.launchMoved}>
                        changed {state.metric.swaps}×
                      </span>
                    )}
                  </button>
                ) : (
                  <div className={styles.launchBox}>
                    <label className={styles.launchLabel} htmlFor="metric-name">
                      Which number means somebody got the value?
                    </label>
                    <div className={styles.launchRow}>
                      <input
                        id="metric-name"
                        className={styles.input}
                        placeholder="paid deposits"
                        maxLength={METRIC_NAME_MAX}
                        value={metricDraft}
                        onChange={(e) => setMetricDraft(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && onNameMetric()}
                      />
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        disabled={busy || !metricDraft.trim()}
                        onClick={onNameMetric}
                      >
                        Set
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

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
                {/* Green only on the same condition the earned line is, which
                    is why it is `earned` and not `have >= need`: a full count
                    with a kind still owed is not a met bar, and a bar that
                    went green there would be the lit door the paragraph below
                    refuses to promise. */}
                <div className={styles.gateBar}>
                  <div
                    className={earned ? styles.gateFillFull : styles.gateFill}
                    style={{
                      width: `${Math.min(100, (gate.have / gate.need) * 100)}%`,
                    }}
                  />
                </div>
                {/* What the phase just cleared banked, on the empty bar of the
                    phase it bought. See `carried`. */}
                {carried && carried.key === gateKey(state) && (
                  <p className={styles.gateCarried}>{carried.text}</p>
                )}
                {/* The bar being met is the one moment this whole product
                    exists to produce, and it used to look exactly like 0/3:
                    same outlined button, same words, nothing said. A builder
                    could stand here for days having already earned the next
                    phase and never be told. Refusals got ninety words; this
                    got none. */}
                {/* `owed` is why this isn't just have >= need. BUILD asks for
                    two proofs AND one of them being a real user touching the
                    thing, so the count can be full while the phase is not met
                    — and promising "Earned" there would be a lit door that
                    doesn't open, on the product's own word. The count still
                    reads 2/2, because it is: the nights are banked and stay
                    banked. What's left is named instead. */}
                {earned ? (
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
                  <>
                    {/* The count is full and a KIND is still owed — the one
                        case where the number above says nothing is missing.
                        Said here rather than left to the refusal, because the
                        refusal only arrives once the button has been pressed,
                        and a builder reading 2/2 has no reason to press it. */}
                    {gate.have >= gate.need && gate.owed.length > 0 && (
                      <p className={styles.gateOwed}>
                        The count is there. Still needed: {gate.owed.join("; ")}.
                      </p>
                    )}
                    {/* The other half of the same problem, and the worse half:
                        VALIDATION's number counts people, so three accepted
                        nights about one hostelmate read 1/3 with nothing on
                        screen saying why. That is the meter appearing to have
                        lost two nights of banked work — the one thing it must
                        never look like. Says what is on the record first and
                        what is missing second, the same order as the line
                        above and as the refusal. */}
                    {gate.banked > gate.have && (
                      <p className={styles.gateOwed}>
                        {gate.banked} proofs banked,{" "}
                        {gate.have === 1 ? "1 person" : `${gate.have} people`}.{" "}
                        {goal.phase}{" "}
                        counts people — tonight&apos;s has to be someone new.
                      </p>
                    )}
                    {/* Still pressable below the bar, on purpose: Django counts
                        the rows and answers, and being told exactly what is
                        missing is the coaching.

                        Emphasis is the part that moves. At `have === 0` this is
                        the only button on the goal card, 34px tall and
                        marigold-outlined — the loudest control on the product's
                        main screen on a builder's first morning, and the only
                        thing it can produce there is a refusal. There is also
                        nothing for that refusal to add: the bar above already
                        reads 0/1, the phase hint already says what the work is,
                        and the gate's detail at zero can only restate them.

                        So below anything at all it takes the weight `close this
                        goal` has — available, not advertised — and it is a
                        button again the moment one proof is banked. Deliberately
                        `have === 0` rather than "below the bar": a builder at
                        1/3 has evidence on the record and a real question about
                        what is left, and the refusal at 2/3 names WHICH piece is
                        missing, which is worth a button.

                        Quiet is where it stops. `.advanceLink`, not
                        `.retireLink`: it took the exits' class to get the look
                        and took their exemption from the 44px floor with it,
                        which left the forward move a 28.5px target on the one
                        morning it is the only thing on the card. It looks the
                        same and it is 44px again. `.retireLink` is the two
                        doors' own class, and this is not a door. */}
                    <button
                      className={
                        gate.have === 0 ? styles.advanceLink : styles.secondaryBtn
                      }
                      disabled={busy}
                      onClick={onAdvance}
                    >
                      Request phase advance
                    </button>
                  </>
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

            {/* At TRACTION with TRACTION's own proof on the record, finishing
                is the expected move, so it gets a real button. Everywhere else
                it lives behind the quiet link — available, just not advertised.

                It used to read "Close this out", which is what you say about a
                ticket. This button cannot appear unless at_finish_line is true,
                and that means the record already holds accepted proof stamped
                TRACTION — somebody came back on their own, or paid — so the
                words are the database talking, not praise, and talking about
                this phase rather than the proofs that paid to reach it. It read
                LAUNCH until TRACTION landed behind it, which is the same
                correction twice: the post going out was never the finish
                either. Same earned line and primary button as the gate one
                screen up, because it is the same kind of moment.

                It invites the claim rather than declaring the win: the box it
                opens still asks what happened and can still end in "I'm
                dropping it". And the quiet link below stays neutral on purpose
                — it is the way out for an idea that died too, and nobody should
                have to click a victory to quit. */}
            {state.atFinishLine && !retiring && (
              <>
                <p className={styles.gateEarned}>
                  Earned. Proof is on the record.
                </p>
                <button
                  className={styles.primaryBtn}
                  onClick={() => setRetiring(true)}
                >
                  Claim the win
                </button>
              </>
            )}

            {/* Two doors, and the quieter one is deliberately first. Until now
                the only way to get a room back was to retire the goal, which
                made burying the idea the cheapest route to reconsidering it —
                in a product whose whole argument is that closing something
                honestly is fine. Reconsidering is not closing, and it should
                not have to be spelled `close this goal` to be reachable.

                Both stay quiet links: neither is the move being recommended,
                and the loudest thing on this card is still the day's work. */}
            {!retiring && !reopening ? (
              <div className={styles.doors}>
                <button
                  className={styles.retireLink}
                  onClick={() => setReopening(true)}
                >
                  {ws?.messages.length
                    ? "back to the room"
                    : "not sure about this one?"}
                </button>
                <button
                  className={styles.retireLink}
                  onClick={() => setRetiring(true)}
                >
                  close this goal
                </button>
              </div>
            ) : reopening && !retiring ? (
              /* The reopened room, in the place the retire box would have
                 opened — because it is the alternative to it, not a feature
                 somewhere else. Nothing in it banks, nothing advances, and
                 gates.py never reads it: the same terms the room before the
                 goal has always run on, with a smaller meter. */
              <>
                <Workshop reopened {...room} />
                <button
                  className={styles.retireLink}
                  onClick={() => setReopening(false)}
                >
                  back to the day
                </button>
              </>
            ) : (
              <div className={styles.retireBox} ref={retireBoxRef}>
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
                      a thing the server gets to disallow.

                      Neither of them is the default below the finish line. The
                      filled marigold button, first in reading order, used to be
                      "I achieved it" — on a goal whose own counter says the
                      phase is unfinished and whose record holds no finish-line
                      proof. The product already knows when achievement is the
                      expected move and already says so one screen up:
                      atFinishLine lights "Earned. Proof is on the record." and
                      a real "Claim the win". Everywhere else this was a filled
                      button inviting a claim the record will quietly contradict
                      — at the one moment a builder is deciding how to describe
                      a thing that did not work, in prose that goes on the
                      record permanently and that the coach then reacts to.

                      It stays first. It is not the shameful option and must not
                      read as one; it just stops being the recommended one. The
                      verdict was never the builder's anyway — gates.reads_as
                      computes it from proofs they had to earn, so a flattering
                      self-classification buys nothing on the record. */}
                  <button
                    className={
                      state.atFinishLine ? styles.primaryBtn : styles.secondaryBtn
                    }
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
                  {/* The third exit, and the one the journey actually takes
                      most often between VALIDATION and BUILD: the idea dies
                      and the problem survives. It closes exactly as "I'm
                      dropping it" does — same ABANDONED row, same computed
                      verdict, and a pivot with no contact proofs behind it
                      still reads UNTESTED, because calling it a pivot is not
                      evidence of anything.

                      What it changes is the next screen: the goal they commit
                      to there is linked back to this one, so the coach opens
                      knowing what those weeks of interviews found. Until now
                      the product's memory of them died with the goal, which
                      made the honest move cost more than limping on. */}
                  <button
                    className={styles.secondaryBtn}
                    disabled={busy || !retireReason.trim()}
                    onClick={() => onRetire("ABANDONED", { pivot: true })}
                  >
                    Same problem, new idea
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

          {/* The second card in the DOM and the first one on a phone — see
              .todayCard, which lifts it above the goal card inside the
              single-column block. The class is here only to be named there:
              ordering by :nth-child would break the moment a card is inserted
              above it. */}
          <section className={`${styles.card} ${styles.todayCard}`}>
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
                {/* Today's task as Masterji heard it, written from work the
                    builder already described in chat. The morning's half of the
                    bargain the evening has had all along: he writes it down,
                    they press the button. Nothing here declares anything, and
                    the server would not let it — the draft lives on the goal
                    precisely because no check-in exists until Declare it is
                    pressed.

                    ABOVE the prompt, for the reason the proof draft sits above
                    the ask: this is the answer and "One task, out loud" is the
                    question, and a card that asks first makes the builder read
                    a request they have already answered before it will show
                    them the answer.

                    It renders only in this branch, which is the branch with
                    nothing declared — so it can never appear where "Declared:"
                    goes. That is the guard, and it is structural rather than a
                    condition somebody has to maintain. */}
                {state.declarationOffer && (
                  <div className={styles.proofOffer}>
                    <p className={styles.proofOfferLabel}>
                      Masterji heard today&apos;s task
                    </p>
                    <p className={styles.proofOfferText}>
                      {state.declarationOffer}
                    </p>
                    <button
                      className={styles.proofOfferBtn}
                      onClick={() => {
                        setAmText(state.declarationOffer);
                        amBoxRef.current?.focus();
                      }}
                    >
                      Use this — edit it below if it&apos;s not right
                    </button>
                  </div>
                )}
                <p className={styles.todayPrompt}>
                  Morning. One task, out loud:
                </p>
                <textarea
                  ref={amBoxRef}
                  className={styles.textarea}
                  rows={2}
                  placeholder="Today I will…"
                  value={amText}
                  onChange={(e) => setAmText(e.target.value)}
                />
                <div className={styles.declareRow}>
                  <button
                    className={styles.primaryBtn}
                    disabled={busy}
                    onClick={() => onDeclare()}
                  >
                    Declare it
                  </button>
                  <DueHourSelect value={amHour} onChange={setAmHour} />
                </div>
              </>
            ) : !today.pmProofText || isUnsettled(today.proofStatus) ? (
              <>
                {/* Their own word, read back while it is still about
                    something. Without this the hour would be a control whose
                    value the builder can never see again, which is the
                    definition of decorative — and it is the coach's only
                    lever here, so the card and the prompt have to be looking
                    at the same fact. Deliberately absent from the settled
                    branch below: once the proof is in, the hour is spent, and
                    a filing time is not what that line is for. */}
                <p className={styles.declared}>
                  Declared: <em>{today.amDeclaration}</em>
                  {today.dueHour !== null && (
                    <span className={styles.declaredHour}>
                      {" "}
                      — by {hourLabel(today.dueHour)}
                    </span>
                  )}
                </p>
                {today.proofStatus === "PUSHED_BACK" && (
                  <p className={styles.pushedBack}>{today.coachReaction}</p>
                )}
                {/* Filed, and nobody read it — the model was unreachable. Not
                    styled as a push-back: nothing was refused, and dressing an
                    outage as a refusal is the one reading that would make a
                    builder stop bringing real work. The proof box below stays
                    open with their words still in it, so "send it again" is
                    the small thing it sounds like. */}
                {today.proofStatus === "UNJUDGED" && (
                  <p className={styles.unread}>{today.coachReaction}</p>
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
                {/* The critique's missing half. Until now the card could say a
                    task was too vague or off-phase and offer nothing to do
                    about it — a problem named in the one room where fixing it
                    is free, under a control that said "File tonight's proof".

                    Quieter than the reaction above it and always below it: the
                    declared task is the builder's and stays the heading, and
                    this is an offer sitting under a criticism, not a correction
                    anybody has to accept. Taking it fills the box and they
                    press Declare it themselves, which re-runs the judgement —
                    so a suggestion accepted verbatim is read back as a
                    declaration rather than trusted as one, and the model does
                    not get to write the wording it will later grade.

                    Hidden while the box is open: it is already in there. */}
                {today.sharpened && !rewording && (
                  <div className={styles.sharpenOffer}>
                    <p className={styles.sharpenOfferLabel}>
                      Sharper, if you want it
                    </p>
                    <p className={styles.proofOfferText}>{today.sharpened}</p>
                    <button
                      className={styles.sharpenOfferBtn}
                      onClick={() => {
                        setAmText(today.sharpened);
                        setAmHour(
                          today.dueHour === null ? "" : String(today.dueHour)
                        );
                        setRewording(true);
                      }}
                    >
                      Use this instead — edit it below if it&apos;s not right
                    </button>
                  </div>
                )}
                {/* Rewording the task on the hook, offered whether or not there
                    is a suggestion under it: the reaction can be right while
                    the sharpening is wrong, and the builder may have their own
                    better sentence. DeclareView has supported this write all
                    along — it updates the open cycle and clears the judgement
                    — and its docstring justifies leaving that endpoint
                    unthrottled on exactly this action, which the card had no
                    way to perform.

                    An EDIT of today's cycle, never a second one. It renders
                    only in this branch, whose condition is a cycle still owing
                    its proof, so the write below lands on that row rather than
                    opening another — "Declare another task" stays the one door
                    into a second cycle. The hour rides along because
                    re-declaring states the whole promise (DeclareView clears an
                    absent one), so it is seeded from the row rather than left
                    blank, which would quietly take back an hour they named. */}
                {rewording ? (
                  <div className={styles.reword}>
                    {/* Three rows, unlike the morning box above, which is two.
                        That one opens empty and grows as somebody types; this
                        one opens with a whole sentence already in it, and at
                        two rows a sharpening long enough to be worth offering
                        arrives with its last line cut in half. Same rule the
                        evening's prefilled box already follows. */}
                    <textarea
                      ref={amBoxRef}
                      className={styles.textarea}
                      rows={3}
                      value={amText}
                      onChange={(e) => setAmText(e.target.value)}
                    />
                    <div className={styles.declareRow}>
                      <button
                        className={styles.primaryBtn}
                        disabled={busy || !amText.trim()}
                        onClick={() => onDeclare()}
                      >
                        Declare it
                      </button>
                      <DueHourSelect value={amHour} onChange={setAmHour} />
                      <button
                        className={styles.linkBtn}
                        onClick={() => {
                          setRewording(false);
                          setAmText("");
                          setAmHour("");
                        }}
                      >
                        leave it as it is
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    className={styles.linkBtn}
                    onClick={() => {
                      setAmText(today.amDeclaration);
                      setAmHour(
                        today.dueHour === null ? "" : String(today.dueHour)
                      );
                      setRewording(true);
                    }}
                  >
                    reword today&apos;s task
                  </button>
                )}
                {/* The morning, finished — and said so, which is the whole
                    change here. This card used to answer a declaration by
                    unfolding the entire evening underneath it: the ask, the
                    box, the link, the attachment and "Submit proof", four
                    fifths of the card, for work that cannot happen for another
                    ten hours. A product that promises two minutes a day cannot
                    end those two minutes on a form.

                    The evening is one press away and every real evening opens
                    it by itself (see eveningOpen), so nothing is buried — what
                    is gone is the homework that used to be handed over at
                    nine in the morning. */}
                {!eveningOpen ? (
                  <>
                    <p className={styles.morningDone}>
                      That&apos;s the morning done. Nothing owed until tonight.
                    </p>
                    <button
                      className={styles.secondaryBtn}
                      onClick={() => setFilingNow(true)}
                    >
                      File tonight&apos;s proof
                    </button>
                  </>
                ) : (
                  <>
                    {/* Masterji's own draft, written from work the builder
                        already described in chat. It says "you've already told
                        me — here it is", and while pieces are still owed it is
                        notes rather than an offer — the same words, doing a
                        different job. This is the only place the builder can
                        SEE that he heard them, which is the whole reason they
                        stop saying it twice, and it has to show the gap in the
                        same breath or a half-finished draft reads as one that's
                        ready to file.

                        ABOVE the ask, not below it. This is the answer and the
                        ask is the question; a card that puts the question first
                        makes the builder read a rule they have already
                        satisfied before it will show them the words that
                        satisfy it. Filed unedited a complete draft skips a
                        second judgement server-side, so the button copies it
                        verbatim rather than reformatting. */}
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
                            <p className={styles.proofGapLabel}>
                              Still needed tonight
                            </p>
                            <ul className={styles.proofGapList}>
                              {owed.map((piece, i) => (
                                <li key={i}>{piece}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {/* The number he heard said, shown inside the draft it
                            came with rather than dropped silently into the box
                            below. A figure that appears in a field the builder
                            did not type into is a figure with no account of
                            where it came from; here it sits under his own
                            wording, in the block whose label already says he
                            wrote this from the conversation.

                            Gated on a named metric because the box it prefills
                            is — "Today's <name>" is the only thing that says
                            what the number is a count of, and the server
                            likewise offers no reading until one is named. */}
                        {state.metric && today.metricOffer !== null && (
                          <p className={styles.proofOfferMetric}>
                            Today&apos;s {state.metric.name}:{" "}
                            <strong>{today.metricOffer}</strong>
                          </p>
                        )}
                        <button
                          className={styles.proofOfferBtn}
                          onClick={() => {
                            setPmText(today.proofOffer);
                            // The number rides the same press as the words, the
                            // way the sharpened task carries its hour: one
                            // draft, one button. Still nothing recorded — this
                            // fills the box, and Submit proof is what files it,
                            // through the same request field a typed number has
                            // always used.
                            if (today.metricOffer !== null) {
                              setPmMetric(String(today.metricOffer));
                            }
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
                    {/* Tonight's reading of the one number, on the evening form
                        because the evening is when a builder knows it. Only once
                        they have named one: the box asks for a reading of
                        something, and "enter a number" with no noun beside it is
                        the app inventing the metric.

                        Left empty every night rather than carried forward from
                        yesterday. A prefilled number is a number nobody counted,
                        and the whole value of the series is that each point is a
                        thing somebody went and looked at. */}
                    {state.metric && (
                      <label className={styles.metricAsk}>
                        {/* The day first, then the name. "<name> today" reads
                            cleanly for "signups" and turns into a run-on the
                            moment the metric is a phrase — and a metric may be
                            sixty characters. */}
                        <span>Today&apos;s {state.metric.name}</span>
                        <input
                          className={styles.input}
                          type="number"
                          min={0}
                          step={1}
                          inputMode="numeric"
                          placeholder="optional"
                          value={pmMetric}
                          onChange={(e) => setPmMetric(e.target.value)}
                        />
                      </label>
                    )}
                    {/* Only offered when the bucket is actually wired, so the
                        form never promises to take something the server would
                        drop. */}
                    {state.uploadsEnabled && (
                      <>
                        {/* The half of the restore that could not be done. Text
                            and link come back from storage; a File cannot go
                            into it, so a builder who attached a screenshot,
                            lost the tab and came back reads their own paragraph
                            exactly as they left it and has no reason to look at
                            the attach row. Worded for everyone it can appear in
                            front of — the form knows a draft was restored, and
                            cannot know whether anything was clipped to it — and
                            in the same words the changelog already used for
                            this. Not a control and not help text about the
                            feature: a fact about the form on screen, which is
                            why it is here and not in the tour. */}
                        {pmRestored && (
                          <p className={styles.attachNote}>
                            Your words came back. An attachment can’t be — if you
                            had a screenshot picked, pick it again.
                          </p>
                        )}
                        <label className={styles.attach}>
                          <input
                            type="file"
                            accept="image/png,image/jpeg,image/webp"
                            onChange={(e) =>
                              setPmImage(e.target.files?.[0] ?? null)
                            }
                          />
                          <span>
                            {pmImage
                              ? `📎 ${pmImage.name}`
                              : "📎 Attach a screenshot"}
                          </span>
                        </label>
                      </>
                    )}
                    <button
                      className={styles.primaryBtn}
                      disabled={busy}
                      onClick={() => onProve()}
                    >
                      {busy && pmImage ? "Masterji is looking…" : "Submit proof"}
                    </button>
                  </>
                )}
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
                     this redirects to a presigned URL on a host that isn't
                     known at build time, so there is nothing to optimise. */
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
                    <div className={styles.declareRow}>
                      <button
                        className={styles.primaryBtn}
                        disabled={busy}
                        onClick={() => onDeclare()}
                      >
                        Declare it
                      </button>
                      <DueHourSelect value={amHour} onChange={setAmHour} />
                    </div>
                  </>
                )}
              </>
            )}
            {/* Last line on the card, under everything the day asks for.
                The nudge is about this box and nothing else, so it lives with
                the box rather than in the control row at the top — both of
                those rows carry a comment saying they are full, and neither
                is where a builder would look for "remind me about tonight".
                Draws nothing at all on a deployment with no VAPID keys set,
                and nothing on a browser that cannot do it. */}
            <NudgeSwitch />
          </section>

          {/* The record, most recent first, cut to a week until asked.

              Every row this goal has ever had used to render here. That is a
              card which grows for as long as the builder keeps their promise:
              at forty days it was a 2,500px wall under Today, and the server
              will hand over ninety. The thing being punished by that was
              turning up — and on a phone, where the dashboard is a single
              scrolling column, it pushed "Behind you" off the end of a page
              nobody scrolls to the bottom of.

              A week is the cut because it is the span the card is actually
              read for: what happened yesterday, and whether the last few days
              hold. Everything older is a question you go looking for, and the
              button is how you ask — nothing is hidden, and the count says
              exactly how much is behind it. */}
          {checkins.length > 0 && (
            <section className={styles.card}>
              <p className={styles.cardLabel}>The record</p>
              {/* The one number, over the days it was read on — at the top of the
                  record because that is what it is: a record, kept by the
                  builder, of the thing they said mattered.

                  Each reading shows the name it was taken UNDER, not the name the
                  metric has now. After a swap the two disagree, and the row is the
                  one that is true about that evening — that difference is the
                  whole of what makes renaming honest instead of silent, and
                  collapsing it here would put the lie back.

                  Only drawn once there is a reading. A named metric with nothing
                  counted yet has no series, and an empty one on the record would
                  be the card describing its own form. */}
              {state.metric && state.metric.series.length > 0 && (
                <div className={styles.metricSeries}>
                  <p className={styles.metricSeriesLabel}>
                    {state.metric.name}
                    {state.metric.held > state.metric.series.length && (
                      <span className={styles.metricSeriesMore}>
                        {" "}
                        · last {state.metric.series.length} of{" "}
                        {state.metric.held}
                      </span>
                    )}
                  </p>
                  <ul className={styles.metricPoints}>
                    {state.metric.series.map((r, i) => (
                      <li key={`${r.date}.${i}`}>
                        <span className={styles.metricPointValue}>{r.value}</span>
                        <span className={styles.metricPointDay}>
                          {formatDay(r.date)}
                        </span>
                        {/* Named only where it differs from what they watch now,
                            because that is the only place it says anything.

                            Bracketed, and that is not softening it. The readings
                            wrap as a flex row, so on the screen "3 · 13 Aug ·
                            paid deposits · 40 · 14 Aug" put the old name between
                            two numbers and read as though it belonged to the
                            second one. Grouping that survives any wrap has to be
                            in the text, not in a gap. */}
                        {r.label !== state.metric!.name && (
                          <span className={styles.metricPointWas}>
                            ({r.label})
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <ul className={styles.history}>
                {(() => {
                  // Which rows, in which order, and whether the cycle column
                  // comes with them — one answer, pinned in lib/record.
                  const { shown, showCycle } = recordSlice(
                    days,
                    cycles,
                    showAllDays,
                    RECORD_PREVIEW,
                  );
                  return shown.map((c) => (
                    <HistoryRow
                      key={c.id}
                      checkin={c}
                      cycle={cycleOf(c)}
                      showCycle={showCycle}
                      onOpen={() => setViewDay(c)}
                    />
                  ));
                })()}
              </ul>
              {daysHeld > RECORD_PREVIEW && (
                <button
                  className={styles.moreDays}
                  onClick={async () => {
                    const opening = !showAllDays;
                    setShowAllDays(opening);
                    // Fetched on the press that needs them, not on load: this is
                    // the whole record of a long goal, and most mornings nobody
                    // asks for it.
                    if (!opening || !daysMissing) return;
                    setAllDaysFailedFor(null);
                    try {
                      const { checkins: rows } = await getGoalHistory(goal.id);
                      setAllDays({ goalId: goal.id, rows });
                    } catch {
                      setAllDaysFailedFor(goal.id);
                    }
                  }}
                >
                  {showAllDays
                    ? `Show the last ${RECORD_PREVIEW}`
                    : `Show all ${daysHeld}`}
                </button>
              )}
              {/* Said out loud rather than left as a short list. A record that
                  quietly hands back fewer days than it just offered is the exact
                  failure this card was fixed for. */}
              {showAllDays && allDaysFailedFor === goal.id && daysMissing && (
                <p className={styles.recordShort}>
                  Couldn&apos;t load the earlier days — showing the {days.length}{" "}
                  most recent of {daysHeld}.
                </p>
              )}
              {/* The live goal, offered here because the artifact is most wanted
                  while the work is still going: an E-Cell application or an
                  interview does not wait for the idea to end. */}
              <TakeTheRecord goalId={goal.id} />
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
            {/* The card, on a log with nothing in it yet. Rare — the welcome
                message is written at goal creation — but a draft with no turn
                to sit under still has to be pressable. */}
            {cardAt === -1 && offer && (
              <CommitCard
                offer={offer}
                metricName={state.metric?.name ?? null}
                busy={busy}
                uploadsEnabled={state.uploadsEnabled}
                url={pmUrl}
                setUrl={setPmUrl}
                image={pmImage}
                setImage={setPmImage}
                onCommit={onCommit}
              />
            )}
            {messages.map((m, i) => (
              // A fragment rather than the bare turn, because the log now
              // holds one thing that is not a turn. The card is a SIBLING of
              // the message it sits under and never a child of it: it is not
              // part of what Masterji said, it is drawn from live state at a
              // position, and burying it inside the bubble is the first step
              // to it being kept alive by one.
              <Fragment key={m.id}>
                {renderTurn(m, i)}
                {i === cardAt && offer && (
                  <CommitCard
                    offer={offer}
                    metricName={state.metric?.name ?? null}
                    busy={busy}
                    uploadsEnabled={state.uploadsEnabled}
                    url={pmUrl}
                    setUrl={setPmUrl}
                    image={pmImage}
                    setImage={setPmImage}
                    onCommit={onCommit}
                  />
                )}
              </Fragment>
            ))}
            {pendingUserMsg && (
              <div data-turn className={styles.userMsg}>
                <p className={styles.msgBody}>{pendingUserMsg}</p>
              </div>
            )}
            {streamingText !== null && (
              <div data-turn className={styles.coachMsg}>
                <span className={styles.avatar}>म</span>
                <p className={styles.msgBody}>
                  {streamingText || <span className={styles.thinking}>…</span>}
                </p>
              </div>
            )}
            {/* Three things to say, while there is nothing to read.

                A new builder met his welcome message, an empty pane and "Talk
                it through…", which is a poor invitation to the habit the rest
                of the product leans on: the draft that makes the evening one
                tap is assembled out of this conversation, so a builder who
                never talks here writes every proof from a blank box. The cold
                start was costing them the warm one.

                Off the moment the builder has spoken IN THIS PHASE — these
                answer "what do I even say to him", and that question comes
                back every time the answer changes. It changes at every gate:
                the server writes a set per phase (guidance.OPENERS) and the
                VALIDATION set is the one that matters most, because the phase
                it opens is the one where a builder has to go and talk to a
                stranger.

                The test used to be `messages.length <= 1`, which is true only
                on a virgin log — so three-quarters of the sets could never be
                reached. Every builder who earned VALIDATION arrived at a full
                log, and "What do I ask so they don't just say yes?" was
                fetched, sent, and dropped on the floor. Reading the phase off
                the messages works because the server stamps it on every row at
                write time and never rewrites it, so a reply from two phases
                ago cannot silence the questions for this one.

                They fill the box rather than sending, like the goal examples
                and the proof draft. A tap that spends a turn is a tap nobody
                can take back, and the words should be theirs by the time they
                reach him. */}
            {!messages.some((m) => m.role === "USER" && m.phase === goal.phase) &&
              !pendingUserMsg &&
              streamingText === null &&
              (guidance?.openers.length ?? 0) > 0 && (
                <div className={styles.openers}>
                  <p id="openers-label" className={styles.openersLabel}>
                    Not sure where to start? Ask him:
                  </p>
                  <ul
                    className={styles.openerList}
                    aria-labelledby="openers-label"
                  >
                    {guidance?.openers.map((opener) => (
                      <li key={opener}>
                        <button
                          type="button"
                          className={styles.opener}
                          onClick={() => {
                            setDraft(opener);
                            composerRef.current?.focus();
                          }}
                        >
                          {opener}
                        </button>
                      </li>
                    ))}
                  </ul>
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
                  if (isSendKey(e)) {
                    e.preventDefault();
                    send();
                  }
                }}
              />
              <button
                className={styles.primaryBtn}
                disabled={streamingText !== null || !draft.trim()}
                onClick={() => send()}
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
                ? /* The one line in the product that narrated the errand this
                     card removes. It said "file it under Today" while the
                     draft, and the press, are now in the log a few inches
                     above — a sentence sending the builder to the other pane
                     for something already in front of them.

                     Today is still named, and named FIRST: it is where the day
                     is recorded and the only box the gate has ever counted, so
                     a builder who reads this line and never scrolls loses
                     nothing. What changes is that the errand stopped being the
                     only route. */
                  "Masterji drafted tonight's proof — file it under Today, or from the card above."
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
                  : /* The same correction, two states late. Credit first,
                       gate second — the rule itself is unchanged and still
                       in the sentence, it just stops being the opening
                       words. Alone and first, "nothing here counts" reads
                       as don't bother typing, and it is false besides: the
                       draft that lands under Today is written from this box
                       and nowhere else.

                       The two differ on what is true yet. _offer_target
                       returns None until there is an am_declaration to hang
                       a draft on, so before one exists he genuinely is not
                       taking notes — that line promises the draft as the
                       thing declaring buys, rather than claiming it is
                       already happening. Says "this conversation" in both,
                       the same words the card uses when it hands the draft
                       back, so the promise and the payoff match. */
                    today?.amDeclaration
                      ? "Masterji writes tonight's proof from this conversation. Nothing counts until you file it under Today."
                      : "Declare today's task under Today — then Masterji writes tonight's proof from this conversation."}
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
          const windowCheckins = newestFirst(checkins.filter((c) => c.phase === viewPhase));
          // ...and the heading now comes from those same rows. It used to be
          // derived from `win` alone — the transitions — so the modal could
          // state a range its own contents fell outside, with the correct list
          // under an incorrect label. The genuine case is the one the comment
          // above names: a proof filed at 00:30 on the night a phase advances
          // lands outside the window that contains it.
          //
          // The open end stays `win`'s to say. A phase the builder is still in
          // ends at "now", and the rows cannot know that — the last of them is
          // a date, not an end.
          const extent = rowsExtent(windowCheckins);
          // Same rule the record card uses, over this drill-in's own rows —
          // see lib/record. A repeat outside them is not visible from here.
          const anyRepeat = anyRepeatIn(windowCheckins, cycles);
          return (
            <div className={styles.modalOverlay} onClick={() => setViewPhase(null)}>
              <div
                ref={phaseDialog}
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
                {/* Two clocks, deliberately: `formatDay` reads CheckIn.date,
                    which is a bare client-local date, and `formatDate` reads a
                    transition's server timestamp on the reader's own clock.
                    The fallback keeps the second because with no rows there is
                    nothing else to say, and the empty branch below says the
                    rest. */}
                <p className={styles.modalMeta}>
                  {extent ? (
                    <>
                      {formatDay(extent.start)} —{" "}
                      {win.end ? formatDay(extent.end) : "now"} · {extent.days}{" "}
                      {extent.days === 1 ? "day" : "days"}
                      {/* Rows are cycles, and a day may hold more than one, so
                          a count of rows cannot be called a count of days. */}
                      {extent.cycles > extent.days && `, ${extent.cycles} cycles`}
                    </>
                  ) : (
                    <>
                      {formatDate(win.start)} — {win.end ? formatDate(win.end) : "now"}
                    </>
                  )}
                </p>
                {windowCheckins.length === 0 ? (
                  <p className={styles.modalEmpty}>
                    No check-ins recorded in this phase.
                  </p>
                ) : (
                  <ul className={styles.history}>
                    {windowCheckins.map((c) => (
                      <HistoryRow
                        key={c.id}
                        checkin={c}
                        cycle={cycleOf(c)}
                        showCycle={anyRepeat}
                        onOpen={() => setViewDay(c)}
                      />
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
          cycle={cycleOf(viewDay)}
          onClose={() => setViewDay(null)}
        />
      )}
    </main>
  );
}
