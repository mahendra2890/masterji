"use client";

// The whole app in one client component (house convention): a dashboard
// column (goal, phase gate, daily loop, history) and the chat with
// Masterji. Server state is one payload from /api/coach/state/; every
// mutation returns enough to patch it, and chat refetches after a turn.

import { useCallback, useEffect, useRef, useState } from "react";
import { signOutAndLeave } from "@/components/AuthGate";
import FailedTries from "@/components/FailedTries";
import Changelog from "@/components/Changelog";
import TakeTheRecord from "@/components/TakeTheRecord";
import ClosedIdea from "./ClosedIdea";
import DeleteAccount from "@/components/DeleteAccount";
import DayDetail from "./DayDetail";
import { updatePrefs, type SessionUser } from "@/lib/auth-client";
import { useDialogFocus } from "@/lib/dialog-focus";
import { readDraft, writeDraft } from "@/lib/drafts";
import { isEarned } from "@/lib/gate";
import { pinLog } from "@/lib/log-pin";
import { cycleOrdinals, newestFirst, ordinalLabel, rowsExtent } from "@/lib/record";
import {
  advanceGoal,
  ApiError,
  createGoal,
  declare,
  formatDay,
  formatDayShort,
  judgeDeclaration,
  getGoalHistory,
  getState,
  localDate,
  phaseWindow,
  prove,
  retireGoal,
  setPhaseIntent,
  setLaunchDate,
  streamChat,
  streamWorkshopChat,
  updateGoalTitle,
  type ChatMessage,
  type CheckIn,
  type CoachState,
  type Phase,
  type Retirement,
} from "@/lib/coach-api";
import styles from "./masterji.module.css";

/** Said when the workshop turns away a fourth candidate. The cap is server
 * code (Workshop.MAX_CANDIDATES), and this is the only thing the refetch after
 * the turn cannot say: the builder watched a suggestion not appear, and silence
 * there reads as the app having dropped their idea rather than having refused
 * it on purpose. */
const REFUSED_PARK =
  "Three is the limit — nothing else got parked. Drop one of these or pick one.";

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

/** Three goals of the right size, for the blank box on somebody's first day.
 *
 * The freeze there is not "I have no ideas" — it is not knowing how big the
 * box wants the answer to be, and a lone placeholder answers that with one
 * data point. Three answer it with a range: two of these are somebody else's
 * world entirely, which is the part that says "yours counts too" better than
 * any sentence could. Deliberately not the placeholder's tiffin app — a
 * fourth phrasing of the example already on screen teaches nothing, and that
 * one goes on to carry the whole guided tour.
 *
 * Kept in the worlds the playbooks and guidance.PROOF_EXAMPLES already talk
 * about — hostel floors, Instagram resellers, a building's own neighbours —
 * so a builder who taps one and reads the coaching afterwards lands somewhere
 * the product has already thought about. The last one earns its place by not
 * being software: nothing else on this screen says a first build is allowed
 * to be a spreadsheet and a WhatsApp group.
 */
const GOAL_EXAMPLES = [
  "Payment tracking for Instagram resellers",
  "A notice board for my hostel floor",
  "Weekend baking orders from my building",
];

/** How much of the record the card shows before it is asked for the rest —
 * see the comment where it is used. Rows, not days: a builder who declares a
 * second task after proving the first gets two rows for one date, and the card
 * would rather show seven rows than promise seven days and count them wrong. */
const RECORD_PREVIEW = 7;

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

/** The hour the evening half of the Today card stops being folded away.
 *
 * Declaring at nine in the morning used to hand the builder the whole evening
 * back in the same breath — the ask, the box, the link field, the attach
 * control and "Submit proof", four-fifths of the card, for work that cannot
 * happen for another ten hours. The product sells two minutes a day and the
 * screen after those two minutes looked like homework.
 *
 * Local, and deliberately the same local day the check-in itself is stamped
 * with (see CheckIn.date) — this is the builder's evening, not the server's.
 * Read at render rather than pinned at mount, so a card left open on a desk
 * since morning has caught up by the time anyone looks at it again.
 *
 * Five is early for an evening on purpose. Being an hour too eager costs a
 * builder one fold they can ignore; being an hour too late costs them the
 * proof, because the card would be hiding the only box that counts at the
 * moment they came to use it.
 */
const EVENING_FROM = 17;

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

/** Whether this keystroke means send, in either of the two boxes that talk to
 * Masterji.
 *
 * One predicate because both used to spell the condition out, and the
 * workshop's copy was missing the `enterSends()` half — so on a phone the room
 * fired a half-written turn where the chat inserted a newline. That is worse in
 * the room than it would be in the chat: a workshop turn is metered
 * (views.WORKSHOP_TURNS), the row is written before the model is called, and
 * the coach's opening move there is to ask for a walk through the builder's
 * last seven days, which is a multi-paragraph answer by design.
 *
 * Takes the fields it reads rather than a React event, so a third box cannot
 * diverge by copying four fifths of the condition again. */
const isSendKey = (e: { key: string; shiftKey: boolean }) =>
  e.key === "Enter" && !e.shiftKey && enterSends();

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
 *
 * The row count is in it for the same reason on a phase that counts people: a
 * second conversation with the same person moves `banked` and not `have`, and
 * the refusal quotes both numbers. Keyed on `have` alone it would sit there
 * saying "3 accepted proofs" over a record that now holds four.
 */
const gateKey = (s: CoachState | null) =>
  s?.goal
    ? `${s.goal.id}:${s.goal.phase}:${s.gate?.have ?? 0}:${s.gate?.banked ?? 0}`
    : "";

/** The way out, with a press between the thumb and the door.
 *
 * It was a 16px-tall underlined link in the top-right of a phone — the thumb's
 * own parking spot — 12px from "What's new", firing on the first press. The
 * cost of that miss isn't a wasted tap: the session is gone and the way back is
 * a full round trip through Google, on the one product whose entire premise is
 * that you come back tomorrow.
 *
 * So: a target you can mean to hit, and a second press. The first press only
 * changes what the button says, which is the cheapest way to make an accident
 * visible, and it undoes itself the moment focus moves — nobody is left holding
 * a question they didn't ask. A timer would do neither well: it either fires
 * while they're still deciding or leaves the question up long after they
 * stopped caring.
 *
 * The underline goes too. It made the exit the only underlined thing in the
 * header, which is a strange honour for the door.
 */
function SignOutButton() {
  const [asking, setAsking] = useState(false);
  return (
    <button
      className={asking ? styles.signOutAsking : styles.signOut}
      onBlur={() => setAsking(false)}
      onKeyDown={(e) => e.key === "Escape" && setAsking(false)}
      onClick={() => (asking ? signOutAndLeave() : setAsking(true))}
      /* The visible label stays inside one fixed box — see .signOut's
         min-width — so the press doesn't slide the rest of the header
         sideways under the finger that made it. The sentence the question
         mark is short for lives here, for anyone not reading pixels. */
      aria-label={asking ? "Press again to sign out" : "Sign out"}
      title={asking ? "Press again to sign out" : undefined}
    >
      {asking ? "sign out?" : "sign out"}
    </button>
  );
}

/** The way back to the tour, from inside the account.
 *
 * /demo/ was reachable from exactly one place — the sign-in popup — so the
 * four screens that explain this product disappeared the moment somebody had
 * an account. That is the wrong way round: a stranger can always press the
 * button again, and the builder who actually needs the explanation is the one
 * three days in, looking at a control whose second option they have never
 * understood. The tour is the only place "Think with me" is explained at all
 * (Tour.tsx says so itself), and it was behind a sign-out.
 *
 * A plain quiet link beside "What's new" rather than anything new: the two
 * are the same kind of thing — a word in the account chrome that opens an
 * explanation — and the mode bar over the composer is a control, not a help
 * page, which is where this emphatically does not go.
 *
 * Padded for the thumb and pulled back by the same amount, the way
 * .historyRow does it: a 24px target that occupies exactly as much of the
 * header as the word does.
 */
function TourLink() {
  return (
    <a
      className={styles.tourLink}
      href="/demo/"
      title="The guided tour of these screens"
    >
      How it works
    </a>
  );
}

/** EN ⇄ हिं. Both languages on screen with the live one lit — a single button
 * reading "EN" states the language you already have and never reveals that the
 * other one exists.
 *
 * A component rather than JSX in the header, because the header was not the only
 * place it belonged and being there alone was a bug. The workshop's system
 * prompt reads `user.tone` too (views.build_workshop_prompt), so the room has
 * always spoken Hinglish — while the only control that sets it rendered inside
 * the goal branch. That made the FIRST conversation a builder ever has with him
 * the one conversation they could not switch, on a product whose pitch is being
 * voiced for India, and Hinglish reachable only after committing the goal the
 * room exists to help someone who cannot commit one yet.
 *
 * Where it goes on the no-goal screen is the footer, on this file's own
 * taxonomy: language is picked once and forgotten, which is account chrome, and
 * the footer is where that screen keeps account chrome. Not over the composer —
 * that slot is for a control reached for mid-conversation, which is the mode.
 */
function ToneSwitch({
  tone,
  busy,
  onSet,
}: {
  tone: CoachState["tone"];
  busy: boolean;
  onSet: (next: CoachState["tone"]) => void;
}) {
  return (
    <div className={styles.toneSwitch} role="group" aria-label="Coach language">
      <button
        type="button"
        className={tone === "ENGLISH" ? styles.toneOptOn : styles.toneOpt}
        aria-pressed={tone === "ENGLISH"}
        disabled={busy}
        onClick={() => onSet("ENGLISH")}
      >
        EN
      </button>
      <button
        type="button"
        lang="hi"
        className={tone === "HINGLISH" ? styles.toneOptOn : styles.toneOpt}
        aria-pressed={tone === "HINGLISH"}
        disabled={busy}
        onClick={() => onSet("HINGLISH")}
      >
        हिं
      </button>
    </div>
  );
}

/** The words a SYSTEM notice is about: the last thing the builder said before
 * it, which is the turn that never landed.
 *
 * Searched backwards rather than read off `i - 1`. What this feeds is a button
 * that SENDS, so the one thing it must never do is put somebody else's sentence
 * in the builder's mouth — and "the row above" is an assumption about how the
 * server writes rows, while "the last thing they said" is the actual question.
 * Empty means no retry button, which is right for a notice with nothing behind
 * it rather than a button that would send "".
 */
const saidBefore = (messages: ChatMessage[], i: number) => {
  for (let n = i - 1; n >= 0; n--) {
    if (messages[n].role === "USER") return messages[n].content;
  }
  return "";
};

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

/** A proof is filed and the cycle is not finished with it. Two ways in, and
 * they are opposites: Masterji read it and wants more (PUSHED_BACK), or he
 * never read it at all (UNJUDGED). Both leave tonight open and both keep the
 * proof box on screen, so every test that used to name PUSHED_BACK alone asks
 * this instead. Mirrors views.UNSETTLED, which decides the same thing for the
 * server — if these two ever disagree, the card and the endpoint disagree
 * about whether the evening is over. */
const isUnsettled = (s: CheckIn["proofStatus"]) =>
  s === "PUSHED_BACK" || s === "UNJUDGED";

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

  // the workshop — the room before the goal, live only on the no-goal screen
  const [wsDraft, setWsDraft] = useState("");
  const [wsStreaming, setWsStreaming] = useState<string | null>(null);
  const [wsPending, setWsPending] = useState<string | null>(null);
  const [wsError, setWsError] = useState("");
  const wsBoxRef = useRef<HTMLTextAreaElement>(null);
  // The room's log, so it can be pinned to the newest turn the way the chat's is.
  const wsLogRef = useRef<HTMLDivElement>(null);

  // forms
  const [goalTitle, setGoalTitle] = useState("");
  // The goal box, so the examples under it can put the caret in it.
  const goalBoxRef = useRef<HTMLInputElement>(null);
  // Rewording the goal. Offered only while the server says nothing is banked
  // against the current wording (goal.titleLocked), so the control is never on
  // screen in a state where pressing it would be refused.
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleText, setTitleText] = useState("");
  const [amText, setAmText] = useState("");
  const [pmText, setPmText] = useState("");
  const [pmUrl, setPmUrl] = useState("");
  const [pmImage, setPmImage] = useState<File | null>(null);
  // The evening's box, so the button that fills it can put the caret in it.
  const pmBoxRef = useRef<HTMLTextAreaElement>(null);
  // Which check-in the evening's box has already been filled from, so the
  // effect below seeds once rather than on every refetch.
  const seededFrom = useRef<number | null>(null);
  // The gate's last answer, and the situation it answered. Rendered only
  // while the two still match — see gateKey above.
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
  // effect: retiring an idea and starting the next one replaces `checkins` in
  // place, and rows held here without a name on them would have gone on
  // rendering the dead goal's record under the new goal's title.
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
  // Which closed goal the next one comes out of, set by "Same problem, new
  // idea" and spent by the commit. Client-side only and deliberately not
  // durable: it is a link the builder just asked for, and a flag that survived
  // a closed tab would silently attach last month's idea to a goal they came
  // back and committed for a different reason.
  const [pivotFrom, setPivotFrom] = useState<number | null>(null);
  const [intentDraft, setIntentDraft] = useState("");
  const [namingPhase, setNamingPhase] = useState(false);
  // The launch date and the room it goes into, and whether the box is open.
  // Both empty by default and never prefilled with a guess: a date the app
  // picked is not a commitment anybody made.
  const [launchDraft, setLaunchDraft] = useState("");
  const [pondDraft, setPondDraft] = useState("");
  const [namingLaunch, setNamingLaunch] = useState(false);
  // Whether the room beside the retire box is showing. Client-side only: the
  // room itself is a server row that exists once the builder has said
  // something in it, and this is just which of the two doors is open.
  const [reopening, setReopening] = useState(false);
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
  // Null until the state payload names a goal — and, for the evening, until
  // there is a task to be evidence for.
  const goalId = state?.goal?.id ?? null;
  const todayId = state?.today?.id ?? null;
  const amKey = goalId === null ? null : `${goalId}.am.${localDate()}`;
  const pmKey = goalId === null || todayId === null ? null : `${goalId}.pm.${todayId}`;
  const chatKey = goalId === null ? null : `${goalId}.chat`;
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
  const unread = state?.today?.proofStatus === "UNJUDGED" ? state.today : null;
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
  }, [state?.messages.length, streamingText, pane]);

  // The same pin for the room's log, which never had one. That log is a 320px
  // window (.workshopLog) on a conversation the server lets run to fifteen
  // turns, so at rest it opened on the OLDEST three: a builder reopening the tab
  // was shown "I don't have an idea yet." as the most recent thing said, with
  // the tiebreak they came back for nearly three screens down inside it — and
  // the tiebreak is the room's whole output, the thing `suggest_goal` is
  // grounded in.
  //
  // `wsPending` counts as arriving, not settled: it is the builder's own line,
  // shown the moment they press send, and the reply is about to land under it.
  useEffect(() => {
    pinLog(wsLogRef.current, wsStreaming !== null || wsPending !== null);
  }, [state?.workshop?.messages.length, wsStreaming, wsPending]);

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
  const fitBox = useCallback(
    (box: HTMLTextAreaElement | null, log: HTMLElement | null) => {
      // display:none, which is how the phone hides whichever pane isn't showing
      // — and how the two rooms hide each other, since only one of them is ever
      // mounted. Nothing to measure there, and measuring anyway writes a 0px
      // height onto the box that the builder then meets when they switch to it.
      if (!box || !box.offsetParent) return;
      const pinned =
        !!log && log.scrollHeight - log.scrollTop - log.clientHeight < 4;
      // Measured back at one row rather than at whatever the last keystroke
      // left it: scrollHeight can't report less than the height already set on
      // the element, so a box that had been tall once could only ever stay tall.
      box.style.height = "auto";
      // scrollHeight counts padding but not border, and box-sizing is
      // border-box repo-wide, so the height we set has to carry the border
      // itself. Read off the element rather than written as 2px — the border is
      // CSS's to change.
      box.style.height = `${box.scrollHeight + box.offsetHeight - box.clientHeight}px`;
      if (log && pinned) log.scrollTop = log.scrollHeight;
    },
    []
  );

  // Both composers, because there are two rooms and the growing box is what a
  // composer IS in this product — the workshop's was two fixed rows with
  // `resize: none`, which is the one place the app told a builder their
  // thinking had a size limit before they had a goal. Only one of the two is
  // ever mounted, and the offsetParent guard above skips the other.
  const fitComposer = useCallback(() => {
    fitBox(composerRef.current, messagesRef.current);
    fitBox(wsBoxRef.current, wsLogRef.current);
  }, [fitBox]);

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
      if (el) fitBox(el, messagesRef.current);
    },
    [fitBox]
  );

  // The workshop's, for the same reason and one of its own: the whole no-goal
  // screen unmounts the moment a goal is committed and mounts again when one is
  // retired, and `wsDraft` survives both.
  const attachWsComposer = useCallback(
    (el: HTMLTextAreaElement | null) => {
      wsBoxRef.current = el;
      if (el) fitBox(el, wsLogRef.current);
    },
    [fitBox]
  );

  // `pane` because the phone mounts this box inside a display:none pane and
  // there is nothing to measure until it shows; window resize because how many
  // lines a paragraph wraps to is a function of width, and a phone turned on
  // its side re-wraps every one of them.
  useEffect(() => {
    fitComposer();
  }, [draft, wsDraft, pane, fitComposer]);

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
      await createGoal(goalTitle.trim(), pivotFrom);
      setGoalTitle("");
      setPivotFrom(null);
      await refresh();
    });

  const onRenameGoal = () =>
    run(async () => {
      const next = titleText.trim();
      // Nothing to say and nothing to write: closing the box IS the answer to
      // an empty edit or the same words back, and a round-trip for either would
      // put "Reworded: X → X" through a server that then declines to log it.
      if (!state?.goal || !next || next === state.goal.title) {
        setEditingTitle(false);
        return;
      }
      await updateGoalTitle(state.goal.id, next);
      setEditingTitle(false);
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

  const onProve = () =>
    run(async () => {
      if (!pmText.trim()) return;
      const filed = await prove(pmText.trim(), pmUrl.trim(), pmImage);
      // Emptying the box is right when the evening is settled — accepted, or
      // pushed back and owed a different answer. An unread proof is neither:
      // nothing was wrong with it, the model just wasn't there, and the only
      // thing being asked for is the same words again. Clearing them would
      // make our outage look like their retype.
      if (filed.checkin.proofStatus !== "UNJUDGED") {
        setPmText("");
        setPmUrl("");
        setPmImage(null);
      }
      await refresh();
    });

  const onAdvance = () =>
    run(async () => {
      if (!state?.goal) return;
      setGateNote(null);
      setCarried(null);
      // The phase being left and what it had banked, read off the state that is
      // about to be replaced. Both are the server's numbers for the phase they
      // describe, which is what makes them still true after the refresh.
      const leaving = state.goal.phase;
      const banked = state.gate?.banked ?? 0;
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
      const after = await refresh();
      const key = gateKey(after);
      setGateNote({ text: detail, key });
      // Only when the phase actually moved. A refusal leaves the bar exactly
      // where it was, and telling a builder their proofs are still on the
      // record while they are looking at the meter that still counts them
      // would be an answer to a question nobody asked.
      if (banked > 0 && after?.goal && after.goal.phase !== leaving) {
        setCarried({
          text: `${banked} proof${banked === 1 ? "" : "s"} from ${leaving} stay on the record.`,
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
      if (!state?.goal || !retireReason.trim()) return;
      const closing = state.goal.id;
      const { retirement } = await retireGoal(
        closing,
        retireReason.trim(),
        outcome
      );
      setPivotFrom(opts.pivot ? closing : null);
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
  /** Name what the phase you are standing in will produce. One line, and
   * nothing depends on it: the phase advances on proofs whether this is set,
   * changed or ignored. Re-fetches rather than patching state by hand, because
   * the line goes into the next system prompt and the transcript on screen is
   * about to be read by a coach that has it. */
  const onNamePhase = () =>
    run(async () => {
      const text = intentDraft.trim();
      if (!state?.goal || !text) return;
      await setPhaseIntent(state.goal.id, text);
      setNamingPhase(false);
      setIntentDraft("");
      await refresh();
    });

  /** Name the day it goes in front of people. Append-only server-side: this
   * never edits the last answer, it writes another row, so moving the date
   * leaves the move on the record. Nothing about it can refuse anything. */
  const onNameLaunch = () =>
    run(async () => {
      if (!state?.goal || !launchDraft || !pondDraft) return;
      await setLaunchDate(state.goal.id, launchDraft, pondDraft);
      setNamingLaunch(false);
      await refresh();
    });

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

  /** Say something in the workshop — the room before the goal.
   *
   * Its own sender rather than a branch inside `send`: the two endpoints refuse
   * each other by design (chat 400s without a goal, this one 400s with one), so
   * a single function would spend its life deciding which product it is in. The
   * cap's refusal arrives as a 429 whose detail is the coach's own sentence, and
   * it goes in the same place as any other refusal here. It reads as a notice
   * rather than a fault because the calm version is already under it: by the
   * time this fires, the refetch has zeroed the meter and swapped the composer
   * for the closed-room line. The banner stays because the hourly throttle
   * arrives down this same path and is a genuinely different thing — one says
   * the room is done, the other says come back in a bit. */
  const sendWorkshop = async (retryOf?: string) => {
    const content = (retryOf ?? wsDraft).trim();
    if (!content || wsStreaming !== null) return;
    if (retryOf === undefined) setWsDraft("");
    setWsError("");
    setWsPending(content);
    setWsStreaming("");
    let spoke = false;
    try {
      await streamWorkshopChat(content, {
        onDelta: (text) => {
          spoke = true;
          setWsStreaming((s) => (s ?? "") + text);
        },
        // The cards are read off the refetch that ends this turn, the same way
        // the evening's draft is: one source of truth, and a card that only
        // existed in the stream can't vanish under the builder's finger. What
        // this handles is the one thing the refetch cannot say — that a fourth
        // candidate was turned away.
        onCandidates: ({ refused }) => {
          if (refused) setWsError(REFUSED_PARK);
        },
        onError: (detail) => {
          if (spoke) setWsError(detail);
        },
      });
    } catch (e) {
      setWsError(e instanceof Error ? e.message : "Something broke.");
    } finally {
      await refresh();
      setWsPending(null);
      setWsStreaming(null);
    }
  };

  if (!state) {
    return <main className={styles.loading}>Masterji is on his way…</main>;
  }

  // Every goal this account has, live one first — what the exit panel offers
  // to hand over before it deletes anything. The export endpoint is per goal,
  // so the offer has to be too; a single "export" button would quietly mean
  // "whichever goal is open", on the one screen where quietly meaning
  // something else is least acceptable.
  const exportableGoals = [
    ...(state.goal ? [{ id: state.goal.id, title: state.goal.title }] : []),
    ...state.archive.map((r) => ({ id: r.goalId, title: r.title })),
  ];

  // Null until the builder's first turn: reading state never opens a room. It
  // is the pre-goal room on the onboarding screen and this goal's one
  // reopening on the dashboard — the same endpoint, the same transcript, the
  // same meter, and the server decides which from the builder's own state.
  const ws = state.workshop;
  const roomTurnsLeft = ws ? ws.turnsLeft : state.workshopTurns;

  /** The room, drawn once for both of the screens that can hold one.
   *
   * A function rather than a component so it keeps the refs it is given: a
   * nested component would be a new type on every render, remounting the
   * composer and taking the caret out of it mid-sentence.
   *
   * What differs between the two is copy and one block — the reopened room has
   * no openers, because "start with:" is for a builder who has nothing, and
   * this one has a goal, a phase and three weeks of record. What does not
   * differ is everything the room IS: the meter, the transcript, the composer,
   * and that nothing in it banks. */
  const renderRoom = (reopened: boolean) => (
    <section className={styles.workshop}>
      <div className={styles.workshopHead}>
        <p className={styles.workshopTitle}>
          {roomTurnsLeft === 0 && ws
            ? reopened
              ? "Room closed."
              : "Workshop closed."
            : reopened
              ? "Still the right idea? Say it out loud."
              : "Not sure yet? Think it through with him."}
        </p>
        {/* The meter is the mechanism, so it is on screen BEFORE the first
            turn, not from the second: a room whose hard end only announces
            itself once you are near it is a trapdoor. Both numbers are the
            server's — turnsLeft is computed there so this and the refusal can
            never disagree, and the budget is sent even with no room open
            precisely so this line can exist at rest. The reopened room's
            budget is smaller and the server says which it is sending. */}
        {state.workshopTurns > 0 && (
          <p className={styles.workshopTurns}>
            {roomTurnsLeft} of{" "}
            {ws ? ws.turnsTotal : state.workshopTurns} turns left
          </p>
        )}
      </div>

      {(ws?.messages.length || wsPending !== null) && (
        <div className={styles.workshopLog} ref={wsLogRef}>
          {ws?.messages.map((m) =>
            /* A turn that never landed, in the log's one shape that belongs
               to neither speaker — the same dashed pill the chat uses,
               because it is the same event: the app saying a turn broke. It
               used to be drawn as something Masterji said. */
            m.role === "SYSTEM" ? (
              <div key={m.id} data-turn className={styles.systemMsg}>
                <p className={styles.systemText}>{m.content}</p>
              </div>
            ) : (
              <div
                key={m.id}
                data-turn
                className={m.role === "USER" ? styles.userMsg : styles.coachMsg}
              >
                {m.role === "COACH" && <span className={styles.avatar}>म</span>}
                <p className={styles.msgBody}>{m.content}</p>
              </div>
            )
          )}
          {wsPending !== null && (
            <div data-turn className={styles.userMsg}>
              <p className={styles.msgBody}>{wsPending}</p>
            </div>
          )}
          {wsStreaming !== null && (
            <div data-turn className={styles.coachMsg}>
              <span className={styles.avatar}>म</span>
              <p className={styles.msgBody}>
                {wsStreaming || <span className={styles.thinking}>…</span>}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Openers, while the room is still silent. Same bargain as the phase
          openers in chat: tapping fills the box and leaves the sending — and
          the editing — with the builder. Tapping the first one is also how the
          coach learns they arrived empty-handed, which is the one case his
          week-walk is the right opening move for.

          Not in the reopened room. Its builder is not short of a first
          sentence — they came in with one, and it is the whole reason the
          room exists. */}
      {!reopened &&
        !ws?.messages.length &&
        wsPending === null &&
        state.workshopOpeners.length > 0 && (
          <div className={styles.openers}>
            <p id="ws-openers-label" className={styles.openersLabel}>
              Start with:
            </p>
            <ul className={styles.openerList} aria-labelledby="ws-openers-label">
              {state.workshopOpeners.map((opener) => (
                <li key={opener}>
                  <button
                    type="button"
                    className={styles.opener}
                    onClick={() => {
                      setWsDraft(opener);
                      wsBoxRef.current?.focus();
                    }}
                  >
                    {opener}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

      {wsError && <p className={styles.error}>{wsError}</p>}

      {/* No composer once the turns are gone. The refusal is already on screen
          above as the coach's own words, and leaving a box there that only ever
          answers 429 is the product pretending a door is open. */}
      {/* The {" "} in both closed-door sentences is load-bearing and must not be
          reformatted away — see the same note in Landing.tsx and Tour.tsx.
          Written as `{turns} turns, done.` it shipped as "15turns, done." for
          as long as the room has existed: the text node after the expression
          wraps to the next source line, and the build drops the space at the
          front of it. The one sentence that has to send a builder somewhere,
          with a typo in its first word. */}
      {ws && roomTurnsLeft === 0 ? (
        reopened ? (
          <p className={styles.workshopSpent}>
            {state.workshopTurns}{" "}
            turns, and this room opens once per goal. Nothing in here touched
            your record. Finish the bar in front of you, sharpen the wording, or
            close it today — yours to pick.
          </p>
        ) : (
          <p className={styles.workshopSpent}>
            {state.workshopTurns}{" "}
            turns, done. You don&apos;t need a better idea — you need one you
            can test. Put it in the box above.
          </p>
        )
      ) : (
        /* The chat's composer band, not a second one. Two fixed rows with
           `resize: none` was the room telling a builder their answer had a size
           before they had said anything — in the one conversation where the
           useful answer is long. It grows a line at a time now, up to the same
           cap, through the same fitComposer.

           Send stays `secondaryBtn`. That is the safeguard on all of this: the
           room may speak the chat's language, but the one filled control on
           whichever screen it is sitting on is not this. */
        <div className={styles.composer}>
          <div className={styles.composerRow}>
            <textarea
              ref={attachWsComposer}
              className={styles.composerInput}
              placeholder={
                reopened
                  ? "I'm not sure this is worth it any more…"
                  : "I don't know what to build yet…"
              }
              value={wsDraft}
              /* The resting height, not the height — see the same note on the
                 chat composer. */
              rows={1}
              maxLength={2000}
              disabled={wsStreaming !== null}
              onChange={(e) => setWsDraft(e.target.value)}
              onKeyDown={(e) => {
                if (isSendKey(e)) {
                  e.preventDefault();
                  void sendWorkshop();
                }
              }}
            />
            <button
              type="button"
              className={styles.secondaryBtn}
              disabled={wsStreaming !== null || wsDraft.trim() === ""}
              onClick={() => void sendWorkshop()}
            >
              Send
            </button>
          </div>
        </div>
      )}
    </section>
  );

  /* --- onboarding / just-retired ---------------------------------------- */
  if (!state.goal) {
    const closing = justRetired ?? state.archive[0];
    const shipped = closing?.outcome === "COMPLETED";
    // The box holds words that are theirs, not one of ours — see the buttons.
    const examplesSpent =
      goalTitle.trim() !== "" && !GOAL_EXAMPLES.includes(goalTitle);
    // Two columns once there is a conversation to put in the second one, and
    // the centred single column — the screen every builder lands on, tuned
    // against a real first impression — until then. The room's state (the
    // meter, the pile, the forecast) is the left column's with the box it
    // fills; the conversation is the right column's. That is the post-goal
    // shape, and this screen was holding all of it in one 520px stack with a
    // 320px window cut in the middle of it.
    const roomOpen = !!(ws?.messages.length || wsPending !== null);
    return (
      <main className={styles.onboarding} data-room={roomOpen ? "open" : "shut"}>
        {/* The commit side. Sticky at the top of its column so that every
            sentence the room produces pointing "up at the box" is true at the
            moment it is read: the closing line names it, `parkedLabel` says
            "tap to put it in the box", and WORKSHOP_SYSTEM tells the coach to
            say "the box is right there". Measured before this: at 375×812 with
            the turns spent, that closing line and the box it names were 913px
            apart on an 812px viewport, so the two could not be on screen
            together. It also strengthens the hierarchy the room was built
            around rather than weakening it — the box becomes the only
            permanently visible control on the screen. */}
      <div className={styles.commitSide}>
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
            {/* What this screen used to say last was "you can retire it later,
                but he'll remember" — reversibility and a warning in one breath,
                on the one screen where nobody has done anything yet to be
                warned about. The reversibility is worth saying and stays; the
                threat is spent here and lands properly in the retire flow,
                where there is a record to keep. What the sentence owes instead
                is the shape of what they're agreeing to: a commitment nobody
                has priced reads as unlimited.

                It priced the daily cost and stopped there, which left the
                expensive half unpriced: what they think they are signing up to
                finish. "Pick the one that matters" is a sentence about
                choosing correctly, on the one screen where nobody can yet —
                and the freeze here is not indecision, it is a 19-year-old
                reading the box as a promise to see this through. So the
                sentence says what the server already does: the commitment is
                to TEST the problem, the first step out of IDEA is one evening
                at a desk (gates.PROOFS_REQUIRED[IDEA] is 1, and its bar is
                desk work), and an idea killed by real people reads as tested
                rather than failed. That last one is conditional on purpose:
                reads_as needs INVALIDATED_AT contact proofs before it says
                "tested → dead", so the promise is about dying in front of
                people, never about closing. */}
            <p className={styles.onboardSub}>
              Pick the problem you&apos;ll test first — not the idea you&apos;ll
              finish. Then it&apos;s one task each morning and proof of it each
              evening, about two minutes a day.
            </p>
            {/* Split rather than cut: every sentence below earned its place
                against a real failure, and none of them is gone. What changed
                is when they arrive. All five jobs used to land as one block at
                the moment of least investment — 223px and 90 words at 390×844,
                a quarter of the viewport, in front of somebody who has just
                handed over a Google account and typed nothing — which is the
                shape of a terms-and-conditions wall above the box.

                The two that stay above are the two the commit is actually a
                commitment to: test first rather than finish, and the daily
                price. The rest is what a hesitating builder goes LOOKING for,
                which is what a disclosure is for — closed it costs a line, and
                the answer is one tap from the box it is about. */}
            <details className={styles.onboardMore}>
              <summary>What you&apos;re agreeing to</summary>
              <p>
                Masterji coaches one thing at a time. The first thing he asks
                for is one evening at your desk. You can close it whenever you
                like, and an idea that dies in front of real people reads as
                tested on your record — most first ones should.
              </p>
            </details>
          </>
        )}

        <div className={styles.onboardForm}>
          <input
            ref={goalBoxRef}
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

        {/* First run only — `closing` is set by an archive entry as well as by
            a just-retired goal, so this is off for everyone who has done this
            before. They know the shape; the examples would be clutter, and the
            screen they're on is a victory lap.

            These fill the box rather than committing: the goal has to be
            theirs, and one tap from "example" to "locked in a database
            constraint" is how you get a user coached on somebody else's idea.
            Filling it leaves the edit — and the decision — with them. */}
        {!closing && (
          <div className={styles.examples}>
            <p id="goal-examples-label" className={styles.examplesLabel}>
              Roughly this specific:
            </p>
            {/* Named by the line above rather than by three aria-labels: the
                buttons say a goal each, and what a goal is doing in a button
                is the one thing their own text can't carry. */}
            <ul className={styles.exampleList} aria-labelledby="goal-examples-label">
              {GOAL_EXAMPLES.map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    className={styles.example}
                    /* Spent once the goal is theirs. Filling the box would
                       throw away a sentence they typed, and it does not come
                       back: setting a controlled input's value through React
                       takes the browser's own undo stack with it, so Ctrl+Z
                       returns the example, not their words. Verified, not
                       assumed.

                       Dimmed rather than unmounted, because this column is
                       centred: dropping the block the moment they start typing
                       re-centres everything and slides the box out from under
                       the cursor they are typing into. Switching between
                       examples stays live — swapping one example for another
                       costs nothing. */
                    disabled={examplesSpent}
                    onClick={() => {
                      setGoalTitle(example);
                      // And put them in the box it filled — the same move the
                      // evening's draft button makes, for the same reason. The
                      // whole promise of an example is "now make it yours",
                      // and that is a lie if editing starts with a hunt for
                      // the caret.
                      goalBoxRef.current?.focus();
                    }}
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Said out loud, because a link the builder cannot see is a link they
            cannot decline. What carries over is what they LEARNED — the people
            they spoke to and what those people said, as facts the coach is
            handed — and nothing they earned: the new goal starts at IDEA with
            nothing banked and its first proof is owed exactly as if this were
            their first day.

            Droppable in one press. They asked for it thirty seconds ago on the
            previous screen, and by the time they have typed a title they may
            have decided this is a different problem after all. */}
        {pivotFrom !== null && closing && (
          <p className={styles.carrying}>
            Carrying what you learned on{" "}
            <strong>{closing.title}</strong> — the conversations, not the
            counts. This one still starts at IDEA.{" "}
            <button
              type="button"
              className={styles.carryingOff}
              onClick={() => setPivotFrom(null)}
            >
              start clean instead
            </button>
          </p>
        )}

        {error && <p className={styles.error}>{error}</p>}

        {/* What the room has produced FOR the box, next to the box. Both of
            these came out of the conversation and both of them are about the
            commit rather than about the talking, which is why they moved out
            of the log's column: the pile is what you pick from and the
            forecast is what picking would cost. */}

        {/* Parked candidates, and the one his tiebreak landed on. Both fill
            the commit box and neither commits — the goal-examples bargain,
            which exists because one tap from "his suggestion" to a database
            constraint is how a builder ends up coached on somebody else's
            idea. The pile is capped at three server-side; nothing here
            enforces it, and nothing here needs to. */}
        {ws && (ws.candidates.length > 0 || ws.suggestedTitle) && (
          <div className={styles.parked}>
            <p id="parked-label" className={styles.parkedLabel}>
              {ws.candidates.length >= ws.maxCandidates
                ? `Three parked — that's the lot. Pick one:`
                : `Parked (${ws.candidates.length}/${ws.maxCandidates}) — tap to put it in the box:`}
            </p>
            <ul className={styles.parkedList} aria-labelledby="parked-label">
              {ws.suggestedTitle && (
                <li key="suggested">
                  <button
                    type="button"
                    className={styles.parkedPick}
                    onClick={() => {
                      setGoalTitle(ws.suggestedTitle);
                      goalBoxRef.current?.focus();
                    }}
                  >
                    {ws.suggestedTitle}
                    <span className={styles.parkedPickNote}>his pick</span>
                  </button>
                </li>
              )}
              {ws.candidates.map((c) => (
                <li key={c}>
                  <button
                    type="button"
                    className={styles.parkedItem}
                    onClick={() => {
                      setGoalTitle(c);
                      goalBoxRef.current?.focus();
                    }}
                  >
                    {c}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* What committing would cost, in IDEA's own four parts. Under the
            cards because it is about the candidate they are circling, and a
            readout rather than a control: every number in it was counted by
            the server off what the coach extracted, the same transfer bar.py
            makes one screen later.

            Only once something has surfaced. The turn meter in the room's
            header is on screen from turn zero because it is a budget being
            spent and a hard end nobody warned you about is a trapdoor; this is
            the opposite quantity — progress accruing — and "0 of 4" over an
            empty room is a checklist a builder is failing before they have
            said anything. It appears when the first piece lands.

            It never gates. Commit stays the only filled control on the screen
            and works at 0 of 4 exactly as it does at 4. */}
        {ws && ws.sketch.have > 0 && (
          <div className={styles.sketch}>
            <p className={styles.sketchCount}>
              You could already write {ws.sketch.have} of the{" "}
              {ws.sketch.need} pieces IDEA asks for.
            </p>
            <p className={styles.sketchOwed}>
              {ws.sketch.owed.length > 0
                ? `Still open: ${ws.sketch.owed.join("; ")}.`
                : "All four. The first evening's proof is already in this conversation."}
            </p>
          </div>
        )}
      </div>

        {/* --- the workshop ------------------------------------------------
            The room before the goal, and the same activity as the chat pane
            — talking to Masterji — so it is now drawn in the same language.
            Masterji has his face here, his line is unboxed behind it, the
            builder's is the filled one, the body is 15px and the box grows a
            line at a time: every one of those was inverted or absent in the
            first conversation a builder ever has with him.

            What has NOT changed is the hierarchy the room was built with. It
            is still subordinate — Send is still `secondaryBtn` against the
            one filled Commit, the room is still the way in for a builder who
            cannot fill the box rather than the point of the screen, and the
            turn meter is still on screen from turn zero. Grammar and
            hierarchy are separable; this screen was paying for the second
            with the first and getting nothing for it.

            Everything here is a control. What the room is FOR is explained in
            the tour, not in help text wedged between the buttons. */}
        {renderRoom(false)}

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

        {/* The tour matters most here and costs least here: this is the screen
            somebody lands on the moment they finish signing up, with nothing
            on it yet to explain itself, and this row stays quiet rather than
            becoming a full control strip.

            The language switch is the fourth thing in it, and that is a real
            charge against the sentence above — paid because the workshop this
            row sits under has been speaking whichever language it sets all
            along, with no way to say which. It goes LAST so nothing already
            here moves: sign out is deliberately leftmost (see .signOut)
            because its label grows to "sign out?" on the first press, and a
            control that shifts under the thumb mid-confirmation is the one
            thing this row must not do. If the row ever does read as clutter,
            the next place to try is the workshop head beside the turn meter —
            not a caption or a disclosure explaining what the languages are. */}
        <div className={styles.onboardFooter}>
          <SignOutButton />
          <TourLink />
          <Changelog />
          <ToneSwitch tone={state.tone} busy={busy} onSet={onSetTone} />
          {/* The row's own comment says it is at its limit and warns against
              growing it, which this does — and it is worth the charge rather
              than the alternative, which is a product holding a builder's
              diary with a door on only one of its two screens. It goes last
              so nothing already here moves, the same rule the language switch
              was added under. */}
          <DeleteAccount goals={exportableGoals} />
        </div>

        {viewClosed && (
          <ClosedIdea closed={viewClosed} onClose={() => setViewClosed(null)} />
        )}
      </main>
    );
  }

  const { goal, gate, streak, today, checkins, transitions, messages, phases, guidance } =
    state;
  // What the record can render, and what the record actually holds. They differ
  // only past the payload cap, and the count in the button has to be the second
  // one or it is describing the truncation rather than the record.
  const days = allDays?.goalId === goal.id ? allDays.rows : checkins;
  const daysHeld = Math.max(state.checkinsTotal, checkins.length);
  const daysMissing = daysHeld > days.length;
  // Which cycle of its own day each row is. Computed once over the widest set
  // this render holds, because the record card, the phase drill-in and the day
  // panel all show subsets of it and must call the same row the same thing.
  // Not memoised: hooks are illegal this far down the component (the no-goal
  // branch above returns first), and this is a Map over at most the rows
  // already being mapped, filtered and searched inline on this same render.
  const cycles = cycleOrdinals(days);
  const cycleOf = (c: CheckIn) => cycles.get(c.id) ?? 1;
  void justRetired; // consumed by the no-goal branch above
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
  // Today's loop is still open — worth a dot on the pane you can't see.
  const dayOpen =
    !today?.amDeclaration ||
    !today.pmProofText ||
    isUnsettled(today.proofStatus);
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
  // Whether the Today card is showing tonight's half yet.
  //
  // Every clause but the clock is an evening that has already started, so the
  // only builder who meets the folded card is one who declared this morning and
  // has done nothing since — which is exactly who it is for. A push-back is
  // owed work; an earlier try means they were here tonight already; and any
  // proofOffer at all, finished or still gathering, means Masterji has been
  // writing this evening down and hiding that would undo what the running
  // notes are for.
  const eveningOpen =
    filingNow ||
    !today?.amDeclaration ||
    isUnsettled(today.proofStatus) ||
    today.attempts.length > 0 ||
    Boolean(today.proofOffer) ||
    new Date().getHours() >= EVENING_FROM;

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
          {/* Last, and after the exit it is a heavier version of. It is a word
              rather than a control: everything that makes the decision real —
              what goes, and the record offered before the button — is in the
              panel it opens, because a once-ever irreversible action has no
              business being a peer of the language toggle. */}
          <DeleteAccount goals={exportableGoals} />
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

            {/* And under the hint that is the same sentence for every builder
                forever, the one that is theirs. A phase has a bar and no shape:
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
                        missing, which is worth a button. */}
                    <button
                      className={
                        gate.have === 0 ? styles.retireLink : styles.secondaryBtn
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
                {renderRoom(true)}
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
            ) : !today.pmProofText || isUnsettled(today.proofStatus) ? (
              <>
                <p className={styles.declared}>
                  Declared: <em>{today.amDeclaration}</em>
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
                      onClick={onProve}
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
              <ul className={styles.history}>
                {(() => {
                  const ordered = newestFirst(days);
                  const shown = showAllDays ? ordered : ordered.slice(0, RECORD_PREVIEW);
                  const anyRepeat = shown.some((c) => cycleOf(c) > 1);
                  return shown.map((c) => (
                    <HistoryRow
                      key={c.id}
                      checkin={c}
                      cycle={cycleOf(c)}
                      showCycle={anyRepeat}
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
            {messages.map((m, i) => {
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
                  <div key={m.id} data-turn className={styles.digestMsg}>
                    <p className={styles.systemText}>{m.content}</p>
                  </div>
                );
              }
              if (m.role === "SYSTEM") {
                const said = saidBefore(messages, i);
                return (
                  <div key={m.id} data-turn className={styles.systemMsg}>
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
                  key={m.id}
                  data-turn
                  className={m.role === "COACH" ? styles.coachMsg : styles.userMsg}
                >
                  {m.role === "COACH" && <span className={styles.avatar}>म</span>}
                  <p className={styles.msgBody}>{m.content}</p>
                </div>
              );
            })}
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
          const anyRepeat = windowCheckins.some((c) => cycleOf(c) > 1);
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
