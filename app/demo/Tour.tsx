"use client";

// The demo, as a taught tour rather than a canned screenshot.
//
// The old demo showed one frozen screen of the app and left the reader to
// work out what any of it was for. Nobody arrives knowing that this product
// has two text boxes that take the same words and do entirely different
// things with one of them, or that the coach in the chat cannot open the
// gate he keeps talking about. So: one slide per move the builder actually
// makes, the real screen for that move, numbered marks on the parts that
// matter, and the answer to each number in the margin.
//
// Every mock wears the app's own classes from masterji.module.css. Borrowed
// pixels, not redrawn ones — a guide drifts from its product the moment it
// keeps a second copy of the styling.
//
// Copy rule for this file: every number, refusal and worked example here is
// quoted from the thing that produces it — gates.PROOFS_REQUIRED,
// gates.try_advance, guidance.PROOF_HINT/PROOF_EXAMPLES/GATE_NUDGE. If one of
// those changes and this file doesn't, the tour teaches a product that no
// longer exists.

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import Changelog from "@/components/Changelog";
import app from "../masterji.module.css";
import styles from "./demo.module.css";

/* --- annotation ----------------------------------------------------------- */

/** A part of the screen worth pointing at: dashed ring, numbered badge, and
 * the note carrying the same number somewhere in the margin. */
function Mark({
  n,
  grow,
  tight,
  children,
}: {
  n: number;
  /** Take the space the marked control would have taken in a flex row. */
  grow?: boolean;
  /** Shrink-wrap a button, instead of ringing the empty rest of its row. */
  tight?: boolean;
  children: ReactNode;
}) {
  const extra = grow ? styles.markedGrow : tight ? styles.markedTight : "";
  return (
    <div className={`${styles.marked} ${extra}`} data-mark={n}>
      {children}
    </div>
  );
}

/** One line of chat, in the app's own bubbles. */
function Line({ who, children }: { who: "COACH" | "USER"; children: ReactNode }) {
  return (
    <div className={who === "COACH" ? app.coachMsg : app.userMsg}>
      {who === "COACH" && <span className={app.avatar}>म</span>}
      <p className={app.msgBody}>{children}</p>
    </div>
  );
}

/* --- the deck ------------------------------------------------------------- */

type Sample = { verdict: "good" | "bad"; label: string; text: string; why?: string };

type Slide = {
  eyebrow: string;
  title: string;
  kicker: ReactNode;
  /** How the mock and its notes share the width. */
  stage?: "side" | "wide" | "stack";
  caption?: string;
  mock: ReactNode;
  notes?: ReactNode[];
  samples?: Sample[];
  takeaway?: ReactNode;
};

const SLIDES: Slide[] = [
  /* 1 ---------------------------------------------------------------- */
  {
    eyebrow: "The shape of it",
    title: "Four phases. You don't get to skip one.",
    kicker:
      "Masterji coaches one goal at a time, through IDEA → VALIDATION → " +
      "BUILD → LAUNCH. Each phase opens on evidence you banked in the phase " +
      "before it — and the counting is done by the server, not by him.",
    caption: "The goal card",
    mock: (
      <section className={app.card}>
        <p className={app.cardLabel}>The goal</p>
        <Mark n={1}>
          <h2 className={app.goalTitle}>Tiffin-delivery app for my college</h2>
        </Mark>
        <Mark n={2}>
          <ol className={app.stepper}>
            <li className={app.stepDone}>IDEA</li>
            <li className={app.stepNow}>VALIDATION</li>
            <li className={app.stepTodo}>BUILD</li>
            <li className={app.stepTodo}>LAUNCH</li>
          </ol>
          <p className={app.phaseHint}>
            Talk to real customers. Bring notes, not opinions.
          </p>
        </Mark>
        <Mark n={3}>
          <div className={app.gateRow}>
            <span>
              <strong>2</strong>/3 proofs toward BUILD
            </span>
          </div>
          <div className={app.gateBar}>
            <div className={app.gateFill} style={{ width: "66%" }} />
          </div>
        </Mark>
        <Mark n={4} tight>
          <span className={app.secondaryBtn}>Request phase advance</span>
        </Mark>
      </section>
    ),
    notes: [
      <>
        <strong>One goal.</strong>{" "}
        Not three. It&apos;s a database constraint, not a suggestion. You can
        close it whenever you like — the record keeps it either way.
      </>,
      <>
        Where you are, and what this phase is <em>for</em>. Work that
        isn&apos;t this gets flagged the morning you declare it.
      </>,
      <>
        Accepted proofs, counted in the phase you&apos;re standing in:{" "}
        <strong>1</strong> to leave IDEA, <strong>3</strong> conversations to
        leave VALIDATION, <strong>2</strong> working artifacts to leave BUILD.
      </>,
      <>
        Press it as often as you like. Django counts the rows and answers.
        Clicking is not evidence.
      </>,
    ],
    takeaway: (
      <>
        The coach can be argued with. The gate can&apos;t — it&apos;s a{" "}
        <code>WHERE</code> clause in{" "}
        <a
          href="https://github.com/mahendra2890/masterji/blob/main/backend/coach/gates.py"
          target="_blank"
          rel="noreferrer"
        >
          gates.py
        </a>
        , and the LLM only gets to <em>propose</em> an advance.
      </>
    ),
  },

  /* 2 ---------------------------------------------------------------- */
  {
    eyebrow: "Every morning",
    title: "Declare one task, out loud.",
    kicker:
      "Ten seconds, before you touch anything else. This is the thing " +
      "tonight gets judged against — no declaration, nothing to prove.",
    caption: "Today — morning",
    mock: (
      <>
        <section className={app.card}>
          <p className={app.cardLabel}>Today</p>
          <p className={app.todayPrompt}>Morning. One task, out loud:</p>
          <Mark n={1}>
            <div className={`${app.textarea} ${styles.field}`}>
              Interview the mess aunty about what happens at the 9pm rush
            </div>
          </Mark>
          <Mark n={2} tight>
            <span className={app.primaryBtn}>Declare it</span>
          </Mark>
        </section>

        <section className={app.card}>
          <p className={app.cardLabel}>Today — a minute later</p>
          <p className={app.declared}>
            Declared: <em>Set up the database schema for orders</em>
          </p>
          <Mark n={3}>
            <p className={app.offPhase}>
              That&apos;s BUILD&apos;s work and you&apos;re in VALIDATION with
              one conversation left. Nothing stops you doing it — but it
              won&apos;t count toward the gate, and the schema you write
              tonight is a guess about a user you haven&apos;t met.
            </p>
          </Mark>
        </section>
      </>
    ),
    notes: [
      <>
        <strong>One task.</strong>{" "}
        Small enough to finish today, specific enough to prove tonight.
      </>,
      <>
        Filed the moment you press it. Masterji reads it a second later and
        says what he makes of it — the day is already on the record either way.
      </>,
      <>
        Off-phase work is <strong>flagged, never blocked</strong>. He&apos;ll
        tell you it&apos;s the wrong week; the gate is what makes a day spent
        sideways actually cost something.
      </>,
    ],
    samples: [
      {
        verdict: "good",
        label: "A declaration you can prove",
        text: "Interview the mess aunty about what happens at the 9pm rush",
        why: "One person, one topic, and you'll know by tonight whether it happened.",
      },
      {
        verdict: "bad",
        label: "A declaration you can't",
        text: "Work on the app / do research / think about pricing",
        why: "There is no evening version of this that anyone could refuse.",
      },
    ],
  },

  /* 3 ---------------------------------------------------------------- */
  {
    eyebrow: "During the day",
    title: "Talk to him all day. The chat records nothing.",
    kicker:
      "Two boxes in this app take the same free text and do entirely " +
      "different things with it. This one holds a conversation. The one " +
      "under Today holds the day — and it's the only one the gate ever reads.",
    stage: "wide",
    caption: "Masterji — the chat",
    mock: (
      <>
        <div className={styles.headerStrip}>
          <span className={app.toneBtn}>EN</span>
          <span className={app.streak}>4 days 🔥</span>
        </div>

        <div className={styles.chatPanel}>
          <div className={app.messages}>
            <Line who="USER">
              Quick one — should I build this in Next.js or Remix? And Postgres
              or Mongo?
            </Line>
            <Mark n={1}>
              <Line who="COACH">
                Fair question, wrong week. Both of those are BUILD&apos;s
                problem, and neither answer survives a user you haven&apos;t
                met — you have one conversation left before BUILD unlocks. The
                Mom Test says talk about their life, not your idea: go ask the
                hostel mess aunty what she does when orders pile up. Bring me
                notes tonight.
              </Line>
            </Mark>
            <Line who="USER">
              Fine. Can we at least move to BUILD? I feel ready.
            </Line>
            <Mark n={2}>
              <Line who="COACH">
                Ready isn&apos;t the thing I count — let me check the ledger…
                {"\n\n"}
                Not yet. 2/3 accepted proofs in VALIDATION — 1 more before
                BUILD unlocks. One conversation. Ten minutes, someone who
                already has the problem. Ask what they did the last time it
                happened — not whether they&apos;d use your app. Notes tonight.
              </Line>
            </Mark>
          </div>
          <div className={app.composer}>
            <Mark n={3}>
              <div className={app.modeBar}>
                {/* No role and no aria-label, unlike the real control this
                    borrows its classes from: these are spans that cannot be
                    pressed, and the rest of this file marks its mock parts
                    decorative rather than announcing them. The margin note
                    carries the meaning for anyone not looking at the picture. */}
                <div className={app.modeSwitch}>
                  <span className={app.modeOptOn}>Coach me</span>
                  <span className={app.modeOpt}>Think with me</span>
                </div>
                <p className={app.modeCaption}>
                  Assignments and push-back. Switch before there&rsquo;s
                  anything to declare.
                </p>
              </div>
            </Mark>
            <div className={app.composerRow}>
              <div className={`${app.composerInput} ${styles.ph}`}>
                Talk it through…
              </div>
              <span className={`${app.primaryBtn} ${styles.sendBtn}`}>Send</span>
            </div>
          </div>
          <Mark n={4}>
            <p className={app.composerNote}>
              Nothing here counts until you file it under Today.
            </p>
          </Mark>
        </div>
      </>
    ),
    notes: [
      <>
        He&apos;s phase-aware. The answer you get in VALIDATION is not the
        answer the same question gets in BUILD — the playbook for your phase is
        loaded into every reply.
      </>,
      <>
        He <em>asked the server</em>. That refusal is the product working: he
        can propose an advance, Django checks the database and says no.
      </>,
      <>
        Two ways of talking, both yours to set — and both on screen, so
        neither can hide behind the other. <strong>Think with me</strong>{" "}
        trades assignments for questions, for the part of the work that comes
        before there&apos;s anything to declare. <strong>EN → हिं</strong>{" "}
        switches him to Hinglish. Neither one touches the gate.
      </>,
      <>
        The rule lives under the box, not in it. A placeholder is clipped to a
        third of itself on a phone and disappears the moment you start typing —
        which is exactly when this needs saying.
      </>,
    ],
    takeaway: (
      <>
        Use the chat to think. Use <strong>Today</strong>{" "}
        to record. The commonest way to lose an evening is to do real work,
        describe it here, and file nothing.
      </>
    ),
  },

  /* 4 ---------------------------------------------------------------- */
  {
    eyebrow: "The shortcut that isn't a shortcut",
    title: "Tell him what happened. He writes it up.",
    kicker:
      "Translating what you did into what the proof box wanted used to be " +
      "your job, and it's where most evenings died. Now: describe the real " +
      "work in the chat, and if it clears the phase's bar he drafts tonight's " +
      "proof in your own words.",
    stage: "stack",
    mock: (
      <div className={styles.pair}>
        <div className={styles.chatPanel}>
          <div className={app.messages}>
            <Line who="USER">
              Talked to the mess aunty. Says the 9pm rush is 40 plates in 20
              minutes and she just stops taking orders.
            </Line>
            <Mark n={1}>
              <Line who="COACH">
                &quot;She just stops taking orders&quot; — that&apos;s the
                workaround, and it&apos;s the part most builders never reach.
                That clears the bar, so I&apos;ve written it up as
                tonight&apos;s proof. Check it under Today and file it; you
                don&apos;t have to say it again in my words.
              </Line>
            </Mark>
          </div>
        </div>

        <p className={styles.bigArrow}>
          <span className={styles.bigArrowGlyph} aria-hidden="true" />
          <span className={styles.bigArrowLabel}>lands under Today</span>
        </p>

        <section className={app.card}>
          <p className={app.cardLabel}>Today</p>
          <p className={app.declared}>
            Declared: <em>Interview the mess aunty about the 9pm rush</em>
          </p>
          <Mark n={2}>
            <div className={app.proofOffer}>
              <p className={app.proofOfferLabel}>
                Masterji wrote this from your conversation
              </p>
              <p className={app.proofOfferText}>
                Spoke to the mess aunty about the 9pm rush. She gets around 40
                plates of orders inside 20 minutes and can&apos;t cook that
                fast, so she stops taking orders — she doesn&apos;t turn people
                away, she just goes quiet. That&apos;s the workaround today.
              </p>
              <span className={app.proofOfferBtn}>
                Use this — edit it below if it&rsquo;s not right
              </span>
            </div>
          </Mark>
          <Mark n={3}>
            <div className={`${app.textarea} ${styles.field} ${styles.ph}`}>
              Evening proof — what actually happened?
            </div>
          </Mark>
          <Mark n={4} tight>
            <span className={app.primaryBtn}>Submit proof</span>
          </Mark>
        </section>
      </div>
    ),
    notes: [
      <>
        He only drafts when the work already clears the phase&apos;s bar.
        It&apos;s not a way round the bar — it&apos;s him admitting you cleared
        it before you&apos;ve typed it up.
      </>,
      <>
        The draft lands on the check-in, and on a phone the{" "}
        <strong>Today</strong> tab says <em>draft</em>{" "}
        so you don&apos;t miss it on the screen you weren&apos;t looking at.
      </>,
      <>
        Filed unedited it goes <strong>straight through</strong>{" "}
        — he already decided it counted. Edit it and it&apos;s judged again,
        with his draft in front of him.
      </>,
      <>
        The offer records nothing on its own. Pressing submit is yours, and so
        is the credit at the gate.
      </>,
    ],
  },

  /* 5 ---------------------------------------------------------------- */
  {
    eyebrow: "Every evening",
    title: "Proof, or the day doesn't count.",
    kicker:
      "Evidence, not a status update: what you'd show someone who doesn't " +
      "believe you. He's lenient about the writing and strict about whether " +
      "anything happened.",
    caption: "Today — evening",
    mock: (
      <>
        <section className={app.card}>
          <p className={app.cardLabel}>Today</p>
          <p className={app.declared}>
            Declared: <em>Interview the mess aunty about the 9pm rush</em>
          </p>
          <Mark n={1}>
            <div className={app.proofHint}>
              <p>
                What to submit: notes from ONE real conversation — who you
                spoke to, 3 things they said in their own words, what they last
                did about this problem, and what commitment you asked for (and
                whether you got it).
              </p>
              <p className={app.proofExamples}>
                <span className={app.proofOfferBtn}>
                  Show me one that was accepted
                </span>
              </p>
            </div>
          </Mark>
          <Mark n={2}>
            <div className={`${app.textarea} ${styles.field} ${styles.fieldTall}`}>
              Priya, 2nd yr, Block C. Last Tuesday she got back at 22:10, mess
              was shut, paid ₹210 for about ₹90 of food…
            </div>
          </Mark>
          <Mark n={3}>
            <div className={`${app.input} ${styles.ph}`}>Link (optional)</div>
            <div className={styles.fakeAttach}>📎 Attach a screenshot</div>
          </Mark>
          <span className={app.primaryBtn}>Submit proof</span>
        </section>

        <section className={app.card}>
          <p className={app.cardLabel}>Today — pushed back</p>
          <Mark n={4}>
            <p className={app.pushedBack}>
              &quot;Good response&quot; from who? You&apos;ve given me a
              feeling, not a conversation. Names, what they last did about it,
              what you asked them for. Try again — I&apos;ll read this one
              against what I already refused.
            </p>
          </Mark>
        </section>
      </>
    ),
    notes: [
      <>
        What tonight needs, tailored to the task you declared this morning —
        and the phase&apos;s standing ask when the model can&apos;t be reached.
      </>,
      <>
        Don&apos;t know the shape of an accepted answer? He&apos;ll show you a
        real one. It&apos;s folded away because it&apos;s an example, not a
        template to copy.
      </>,
      <>
        A link or a screenshot when there&apos;s something to see. Optional —
        the words are the proof.
      </>,
      <>
        Pushed back is not a punishment and not a cap. Resubmit: he judges the
        new try against every refused one <em>and the words he refused it
        with</em>, so the second look can&apos;t invent a reason the first
        didn&apos;t give.
      </>,
    ],
    samples: [
      {
        verdict: "good",
        label: "Accepted",
        text:
          "Ramesh, mess contractor. Says 40–50 plates go to waste most nights. " +
          "Already tried a WhatsApp group for counts; it died in a week because " +
          "nobody replied by 18:00. Wouldn't share numbers. Gave me an intro to " +
          "the Block B contractor.",
        why: "A person, what they did, what failed, and what you got out of it.",
      },
      {
        verdict: "bad",
        label: "Pushed back",
        text: "Talked to a few people today, good response, everyone said they'd use it.",
        why: "No names, no numbers, nothing anyone actually said — and 'they'd use it' is the one answer that never predicts anything.",
      },
    ],
  },

  /* 6 ---------------------------------------------------------------- */
  {
    eyebrow: "The gate",
    title: "It opens on evidence. Asking doesn't move it.",
    kicker:
      "Every refusal names what's missing and the errand that fixes it — " +
      "because the button reaches the gate with no coach in the loop, and " +
      "that's the exact moment quitting looks reasonable.",
    caption: "Requesting the advance",
    mock: (
      <>
        <section className={app.card}>
          <p className={app.cardLabel}>2 of 3 — refused</p>
          <Mark n={1}>
            <div className={app.gateRow}>
              <span>
                <strong>2</strong>/3 proofs toward BUILD
              </span>
            </div>
            <div className={app.gateBar}>
              <div className={app.gateFill} style={{ width: "66%" }} />
            </div>
          </Mark>
          <span className={app.secondaryBtn}>Request phase advance</span>
          <Mark n={2}>
            <p className={app.gateNote}>
              Not yet. 2/3 accepted proofs in VALIDATION — 1 more before BUILD
              unlocks. One conversation. Ten minutes, someone who already has
              the problem. Ask what they did the last time it happened — not
              whether they&apos;d use your app. Notes tonight.
            </p>
          </Mark>
        </section>

        <section className={app.card}>
          <p className={app.cardLabel}>3 of 3 — open</p>
          <Mark n={3}>
            <ol className={app.stepper}>
              <li className={app.stepDone}>IDEA</li>
              <li className={app.stepDone}>VALIDATION</li>
              <li className={app.stepNow}>BUILD</li>
              <li className={app.stepTodo}>LAUNCH</li>
            </ol>
          </Mark>
          <p className={app.gateNote}>Phase unlocked: VALIDATION → BUILD.</p>
        </section>
      </>
    ),
    notes: [
      <>
        Counted from proofs stamped with the phase you&apos;re in <em>now</em>.
        A proof already spent on unlocking this phase can&apos;t be spent
        again.
      </>,
      <>
        The refusal, then the errand. One conversation — not &quot;keep
        validating&quot;.
      </>,
      <>
        A phase you&apos;ve left closes behind you but stays open to read: tap
        it in the stepper and the days you did there come back, one row at a
        time.
      </>,
    ],
    takeaway: (
      <>
        Every refusal traces to a condition you can read and a test that pins
        it. So does the method behind it —{" "}
        <a
          href="https://github.com/mahendra2890/masterji/tree/main/backend/coach/playbooks"
          target="_blank"
          rel="noreferrer"
        >
          the playbooks
        </a>{" "}
        are about ten minutes of reading, and they credit their sources by
        name.
      </>
    ),
  },

  /* 7 ---------------------------------------------------------------- */
  {
    eyebrow: "What you're building besides the thing",
    title: "The record is the point.",
    kicker:
      "Days accumulate whether or not the idea survives. The record is what " +
      "you leave with — including from an idea you killed on purpose.",
    caption: "The record, and the way out",
    mock: (
      <>
        <section className={app.card}>
          <p className={app.cardLabel}>The record</p>
          <Mark n={1}>
            <ul className={app.history}>
              <li className={app.historyItem}>
                <span className={app.historyRow}>
                  <span className={app.historyDate}>08-06</span>
                  <span className={app.historyText}>
                    Interview the mess aunty about the 9pm rush
                  </span>
                  <span className={app.chipGood}>✓</span>
                </span>
              </li>
              <li className={app.historyItem}>
                <span className={app.historyRow}>
                  <span className={app.historyDate}>08-05</span>
                  <span className={app.historyText}>
                    Interview 2 hostel students about tiffin orders
                  </span>
                  <span className={app.chipGood}>✓</span>
                </span>
              </li>
              <li className={app.historyItem}>
                <span className={app.historyRow}>
                  <span className={app.historyDate}>08-04</span>
                  <span className={app.historyText}>
                    Make a feature list and moodboard
                  </span>
                  <span className={app.chipBad}>✗</span>
                </span>
              </li>
            </ul>
          </Mark>
        </section>

        <section className={app.card}>
          <p className={app.cardLabel}>Closing it out</p>
          <Mark n={2}>
            <p className={app.retirePrompt}>
              What happened? One honest sentence — it goes on the record.
            </p>
          </Mark>
          <div className={`${app.textarea} ${styles.field} ${styles.ph}`}>
            e.g. talked to 6 students, they won&apos;t pay for this.
          </div>
          <Mark n={3}>
            <div className={app.retireActions}>
              <span className={app.primaryBtn}>I achieved it</span>
              <span className={app.secondaryBtn}>I&apos;m dropping it</span>
            </div>
          </Mark>
        </section>
      </>
    ),
    notes: [
      <>
        Every row opens: what you declared, what you filed, the screenshot, the
        tries he refused, and what he said about each one.
      </>,
      <>
        Closing is never blocked, in either direction — and the sentence you
        write is kept next to what the record actually shows.
      </>,
      <>
        How it <em>reads</em>{" "}
        is computed, not claimed. Six conversations and a no comes back as{" "}
        <strong>tested → dead</strong>: validation working, and the result most
        people never get. Dropping it before anyone got a vote reads as{" "}
        <strong>untested</strong>.
      </>,
    ],
  },

  /* 8 ---------------------------------------------------------------- */
  {
    eyebrow: "That's the whole thing",
    title: "A day with Masterji, in four lines.",
    kicker:
      "No dashboard to learn, no settings to tune. One loop, repeated until " +
      "the evidence is in.",
    stage: "stack",
    mock: (
      <>
        <div className={styles.recap}>
          <div className={styles.recapStep}>
            <p className={styles.recapWhen}>Morning</p>
            <p className={styles.recapWhat}>
              Declare one task under <strong>Today</strong>. Ten seconds. He
              tells you if it&apos;s the wrong week&apos;s work.
            </p>
          </div>
          <div className={styles.recapStep}>
            <p className={styles.recapWhen}>During</p>
            <p className={styles.recapWhat}>
              Do it. Think out loud with him when you&apos;re stuck — and
              remember the chat records nothing.
            </p>
          </div>
          <div className={styles.recapStep}>
            <p className={styles.recapWhen}>Evening</p>
            <p className={styles.recapWhat}>
              File the proof under <strong>Today</strong>. If he drafted it
              from your conversation, that&apos;s one tap.
            </p>
          </div>
          <div className={styles.recapStep}>
            <p className={styles.recapWhen}>When the proofs are in</p>
            <p className={styles.recapWhat}>
              The gate opens the next phase. Not before, however well you argue.
            </p>
          </div>
        </div>

        <div className={styles.finish}>
          <Link className={styles.finishBtn} href="/login/">
            Start yours →
          </Link>
          <p className={styles.finishNote}>
            One goal, declared tomorrow morning. Sign in with Google — nothing
            to configure.
          </p>
        </div>
      </>
    ),
  },
];

/* --- the tour ------------------------------------------------------------- */

export default function Tour() {
  const [i, setI] = useState(0);
  const railRef = useRef<HTMLElement>(null);
  // The first render is the reader arriving at the top of the page — only
  // scroll them when THEY moved.
  const moved = useRef(false);

  const go = useCallback((next: number) => {
    setI((cur) => {
      const clamped = Math.max(0, Math.min(SLIDES.length - 1, next));
      if (clamped !== cur) moved.current = true;
      return clamped;
    });
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Not while someone is in a field — the changelog popup and the header
      // both live on this page.
      const el = document.activeElement;
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowRight") go(i + 1);
      if (e.key === "ArrowLeft") go(i - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [i, go]);

  // A slide can be taller than the viewport, so advancing from its foot would
  // otherwise drop the reader into the middle of the next one. The rail rather
  // than the slide: it carries the step count, and a jump that scrolls the
  // control you just pressed off the top of the screen is disorienting.
  useEffect(() => {
    if (!moved.current) return;
    railRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [i]);

  const s = SLIDES[i];
  const last = i === SLIDES.length - 1;
  const stage = s.stage ?? "side";
  const stageClass =
    stage === "wide"
      ? `${styles.stage} ${styles.stageWide}`
      : stage === "stack"
        ? `${styles.stage} ${styles.stageStack}`
        : styles.stage;

  return (
    <main className={styles.page}>
      <div className={styles.banner}>
        A guided tour of the real product — the screens are the app&apos;s own,
        and the refusals in them are the ones the server actually gives.{" "}
        <Link href="/login/">Sign in</Link> to get your own Masterji.
      </div>

      <header className={styles.header}>
        <span className={app.brand}>
          Masterji <span className={app.brandHindi}>मास्टरजी</span>
        </span>
        <div className={styles.headerRight}>
          <Changelog />
          <Link className={styles.cta} href="/login/">
            Start yours →
          </Link>
        </div>
      </header>

      <nav className={styles.rail} aria-label="Tour steps" ref={railRef}>
        {SLIDES.map((slide, n) => (
          <button
            key={slide.title}
            className={n === i ? styles.stepOn : n < i ? styles.stepPast : styles.step}
            aria-label={`Step ${n + 1} of ${SLIDES.length}: ${slide.title}`}
            aria-current={n === i ? "step" : undefined}
            title={slide.title}
            onClick={() => go(n)}
          />
        ))}
        <span className={styles.count}>
          {i + 1} / {SLIDES.length}
        </span>
      </nav>

      <div aria-live="polite">
        <p className={styles.eyebrow}>{s.eyebrow}</p>
        <h1 className={styles.title}>{s.title}</h1>
        <p className={styles.kicker}>{s.kicker}</p>

        <div className={stageClass}>
          <div className={styles.mockCol}>
            {s.caption && <p className={styles.mockCaption}>{s.caption}</p>}
            {s.mock}
          </div>
          {s.notes && (
            <ol
              className={
                stage === "stack" ? `${styles.notes} ${styles.notesUnder}` : styles.notes
              }
            >
              {s.notes.map((note, n) => (
                <li key={n} className={styles.note}>
                  <span className={styles.noteN}>{n + 1}</span>
                  <span className={styles.noteText}>{note}</span>
                </li>
              ))}
            </ol>
          )}
        </div>

        {s.samples && (
          <div className={styles.samples}>
            {s.samples.map((ex) => (
              <div
                key={ex.label}
                className={ex.verdict === "good" ? styles.sampleGood : styles.sampleBad}
              >
                <span className={styles.sampleLabel}>{ex.label}</span>
                <p className={styles.sampleText}>{ex.text}</p>
                {ex.why && <p className={styles.sampleWhy}>{ex.why}</p>}
              </div>
            ))}
          </div>
        )}

        {s.takeaway && <p className={styles.takeaway}>{s.takeaway}</p>}
      </div>

      <div className={styles.nav}>
        <button
          className={app.secondaryBtn}
          disabled={i === 0}
          onClick={() => go(i - 1)}
        >
          ← Back
        </button>
        {/* The last slide carries the sign-in button itself, at the size the
            end of a deck deserves. A second one here would be the same call
            to action twice, 80px apart. */}
        {!last && (
          <button className={app.primaryBtn} onClick={() => go(i + 1)}>
            Next →
          </button>
        )}
        <span className={styles.navSpacer} />
        <span className={styles.navHint}>← → arrow keys work too</span>
      </div>
    </main>
  );
}
