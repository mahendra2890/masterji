"use client";

// The demo: a bridge from the landing page to the sign-in button, not a manual.
//
// Four slides, and the rule that keeps it at four: a slide has to earn its
// place by teaching something a visitor needs BEFORE they sign up and can't
// get anywhere else. That test throws out more than it keeps.
//
// It threw out five slides that were all true and all in the way — the phase
// diagram and the four-line recap of the day, because the landing page says
// both in words and a tour that repeats its own front door is just longer;
// the record and the way to retire a goal, because nobody weighs how they'd
// close a goal before they've made one; and the running proof notes, because
// the screen announces itself ("What Masterji has from your conversation so
// far", "Still needed tonight") to a builder who is already inside. Good
// product UX is a reason to leave something out of the demo, not a reason to
// document it here.
//
// What's left is the three questions someone actually has with their finger
// over the button: what happens in my first two minutes, what does a day look
// like, and is the gate really as unarguable as the landing page claims.
//
// Every mock wears the app's own classes from masterji.module.css. Borrowed
// pixels, not redrawn ones — a guide drifts from its product the moment it
// keeps a second copy of the styling.
//
// Copy rule for this file: every number, refusal and worked example here is
// quoted from the thing that produces it — gates.PROOFS_REQUIRED,
// gates.try_advance, guidance.PHASE_HINT/PROOF_HINT/PROOF_EXAMPLES/GATE_NUDGE,
// views.WELCOME. If one of those changes and this file doesn't, the tour
// teaches a product that no longer exists.
//
// It also starts where the builder does. The deck used to open on a goal
// already three-quarters through VALIDATION, which taught the one phase a
// visitor is guaranteed not to be in: everyone who signs in lands in IDEA, is
// told to write a problem statement, and is told they may not message anyone
// yet. Skipping that made the tour a guide to the middle of the product.

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import Changelog from "@/components/Changelog";
import { SignInButton, SignInProvider } from "@/components/SignIn";
import app from "../masterji.module.css";
import styles from "./demo.module.css";

/* --- annotation ----------------------------------------------------------- */

/** A part of the screen worth pointing at: dashed ring, numbered badge, and
 * the note carrying the same number somewhere in the margin. */
function Mark({
  n,
  tight,
  children,
}: {
  n: number;
  /** Shrink-wrap a button, instead of ringing the empty rest of its row. */
  tight?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={`${styles.marked} ${tight ? styles.markedTight : ""}`}
      data-mark={n}
    >
      {children}
    </div>
  );
}

/** One line of chat, in the app's own bubbles. */
function Line({
  who,
  children,
}: {
  who: "COACH" | "USER";
  children: ReactNode;
}) {
  return (
    <div className={who === "COACH" ? app.coachMsg : app.userMsg}>
      {who === "COACH" && <span className={app.avatar}>म</span>}
      <p className={app.msgBody}>{children}</p>
    </div>
  );
}

/* --- the deck ------------------------------------------------------------- */

type Sample = {
  verdict: "good" | "bad";
  label: string;
  text: string;
  why?: string;
};

type Slide = {
  eyebrow: string;
  title: string;
  kicker: ReactNode;
  /** How the mock and its notes share the width. */
  stage?: "side" | "stack";
  caption?: string;
  mock: ReactNode;
  notes?: ReactNode[];
  samples?: Sample[];
  takeaway?: ReactNode;
};

const SLIDES: Slide[] = [
  /* 1 ---------------------------------------------------------------- */
  {
    eyebrow: "Your first two minutes",
    title: "Commit one goal. He tells you which week you're in.",
    kicker:
      "There is nothing to set up — no plan to upload, no profile, no " +
      "settings. You type the goal, he locks it, and his first message is the " +
      "only work that counts this week and the thing he won't let you do yet.",
    stage: "stack",
    mock: (
      <div className={`${styles.pair} ${styles.pairTop}`}>
        <div className={styles.onboardPanel}>
          <p className={app.wordmark}>मास्टरजी</p>
          <h2 className={app.onboardTitle}>One goal.</h2>
          <p className={app.onboardSub}>
            Masterji coaches one thing at a time — pick the goal that matters
            and commit. You can retire it later, but he&apos;ll remember.
          </p>
          <Mark n={1}>
            <div className={app.onboardForm}>
              <div className={`${app.input} ${styles.ph}`}>
                e.g. Tiffin-delivery app for my college
              </div>
              <span className={app.primaryBtn}>Commit</span>
            </div>
          </Mark>
        </div>

        <p className={styles.bigArrow}>
          <span className={styles.bigArrowGlyph} aria-hidden="true" />
          <span className={styles.bigArrowLabel}>one tap later</span>
        </p>

        <div className={styles.pairStack}>
          <section className={app.card}>
            <p className={app.cardLabel}>The goal</p>
            <h2 className={app.goalTitle}>
              Tiffin-delivery app for my college
            </h2>
            <Mark n={2}>
              <ol className={app.stepper}>
                <li className={app.stepNow}>IDEA</li>
                <li className={app.stepTodo}>VALIDATION</li>
                <li className={app.stepTodo}>BUILD</li>
                <li className={app.stepTodo}>LAUNCH</li>
              </ol>
              <p className={app.phaseHint}>
                Write the problem statement, and where you&apos;d find these
                people — no outreach yet.
              </p>
              <div className={app.gateRow}>
                <span>
                  <strong>0</strong>/1 proofs toward VALIDATION
                </span>
              </div>
              <div className={app.gateBar}>
                <div className={app.gateFill} style={{ width: "0%" }} />
              </div>
            </Mark>
          </section>

          <div className={styles.chatPanel}>
            <div className={app.messages}>
              <Mark n={3}>
                <Line who="COACH">
                  Goal locked: &quot;Tiffin-delivery app for my college&quot;.
                  Rule one: one goal at a time, and this is yours now. You start
                  in IDEA — write a one-paragraph problem statement, then the
                  route to these people: one place they already are, why you
                  think they&apos;re there, and how you&apos;d get one
                  conversation this week. No names needed, and you won&apos;t
                  message anyone until VALIDATION. Talking to me records nothing
                  on its own — declare today&apos;s task under Today, and file
                  your proof there tonight.
                </Line>
              </Mark>
            </div>
          </div>
        </div>
      </div>
    ),
    notes: [
      <>
        <strong>One goal, and that&apos;s the whole setup.</strong> A second one
        is refused by a database constraint, not by a nag. Closing this one is
        always available — it just goes on the record.
      </>,
      <>
        You start in <strong>IDEA</strong> at <strong>0/1</strong>, whatever
        stage you think you&apos;re at. The line under the stepper is what this
        phase is for; the counter is what gets you out of it —{" "}
        <strong>1</strong> accepted proof to leave IDEA, <strong>3</strong>{" "}
        conversations to leave VALIDATION, <strong>2</strong> working artifacts
        to leave BUILD.
      </>,
      <>
        The surprising half is the last line of what he asks for:{" "}
        <strong>you may not message anyone yet</strong>. IDEA is desk work — the
        problem, and the route to the people who have it. Zero conversations
        here isn&apos;t being behind; talking to people is VALIDATION&apos;s job
        and it&apos;s the next thing he unlocks.
      </>,
    ],
    takeaway: (
      <>
        Most tools would let you start building on day one. The first thing this
        one does is tell you which week you&apos;re in — and keep you there
        until there&apos;s evidence.
      </>
    ),
  },

  /* 2 ---------------------------------------------------------------- */
  {
    eyebrow: "Every morning, and all day",
    title: "Two boxes take the same words. Only one counts.",
    kicker:
      "Declare the day's one task under Today: ten seconds, and it's what " +
      "tonight gets judged against. Then talk to him as much as you like — " +
      "the chat is where you think, and it records nothing.",
    stage: "stack",
    mock: (
      <div className={styles.twoUp}>
        <div className={styles.twoUpCol}>
          <p className={styles.mockCaption}>Today — the box that counts</p>
          <section className={app.card}>
            <p className={app.cardLabel}>Today</p>
            <p className={app.todayPrompt}>Morning. One task, out loud:</p>
            <Mark n={1}>
              <div className={`${app.textarea} ${styles.field}`}>
                Interview the mess aunty about what happens at the 9pm rush
              </div>
            </Mark>
            <span className={app.primaryBtn}>Declare it</span>
          </section>

          <section className={app.card}>
            <p className={app.cardLabel}>Today — a minute later</p>
            <p className={app.declared}>
              Declared: <em>Set up the database schema for orders</em>
            </p>
            <Mark n={2}>
              <p className={app.offPhase}>
                That&apos;s BUILD&apos;s work and you&apos;re in VALIDATION with
                one conversation left. Nothing stops you doing it — but it
                won&apos;t count toward the gate, and the schema you write
                tonight is a guess about a user you haven&apos;t met.
              </p>
            </Mark>
          </section>
        </div>

        <div className={styles.twoUpCol}>
          <p className={styles.mockCaption}>
            The chat — the box that doesn&apos;t
          </p>
          {/* The header's own controls, unmarked. A reader can see what they
              are, and neither of them moves the gate — which is the only thing
              about them this deck has to be sure of. */}
          <div className={styles.headerStrip}>
            <span className={app.toneBtn}>EN</span>
            <span className={app.streak}>4 days 🔥</span>
          </div>

          <div className={styles.chatPanel}>
            <div className={app.messages}>
              <Line who="USER">
                Quick one — should I build this in Next.js or Remix? And
                Postgres or Mongo?
              </Line>
              <Mark n={3}>
                <Line who="COACH">
                  Fair question, wrong week. Both of those are BUILD&apos;s
                  problem, and neither answer survives a user you haven&apos;t
                  met — you have one conversation left before BUILD unlocks. The
                  Mom Test says talk about their life, not your idea: go ask the
                  hostel mess aunty what she does when orders pile up. Bring me
                  notes tonight.
                </Line>
              </Mark>
            </div>
            <div className={app.composer}>
              <Mark n={4}>
                <div className={app.modeBar}>
                  {/* No role and no aria-label, unlike the real control this
                      borrows its classes from: these are spans that cannot be
                      pressed, and the rest of this file marks its mock parts
                      decorative rather than announcing them. The margin note
                      carries the meaning for anyone not looking at the
                      picture. */}
                  <div className={app.modeSwitch}>
                    <span className={app.modeOptOn}>Coach me</span>
                    <span className={app.modeOpt}>Think with me</span>
                  </div>
                  <p className={app.modeCaption}>Assignments and push-back.</p>
                </div>
              </Mark>
              <div className={app.composerRow}>
                <div className={`${app.composerInput} ${styles.ph}`}>
                  Talk it through…
                </div>
                <span className={app.primaryBtn}>Send</span>
              </div>
            </div>
            <Mark n={5}>
              <p className={app.composerNote}>
                Nothing here counts until you file it under Today.
              </p>
            </Mark>
          </div>
        </div>
      </div>
    ),
    notes: [
      <>
        <strong>One task</strong>, small enough to finish today and specific
        enough to prove tonight. Filed the moment you press it — he reads it a
        second later and says what he makes of it, but the day is on the record
        either way.
      </>,
      <>
        Off-phase work is <strong>flagged, never blocked</strong>. He&apos;ll
        tell you it&apos;s the wrong week; the gate is what makes a day spent
        sideways actually cost something.
      </>,
      <>
        He&apos;s phase-aware. The answer you get in VALIDATION is not the
        answer the same question gets in BUILD — the playbook for your phase is
        loaded into every reply. <strong>EN → हिं</strong> switches him to
        Hinglish; neither that nor the streak beside it touches the gate.
      </>,
      <>
        {/* The app's own caption is one clause now — "Assignments and
            push-back." — because saying more of it there spent the word the
            note under the composer needed. What the other mode is FOR was
            handed to this deck on purpose; if this note goes, the product
            explains the toggle nowhere. */}
        <strong>Think with me</strong> trades assignments for questions and puts
        options on the table instead — for the part of the work that comes
        before there&apos;s anything to declare. It stays set until you change
        it, on every device, and it moves the gate by nothing.
      </>,
      <>
        The rule, where you can&apos;t miss it. Everything above this line is a
        conversation; the day is recorded under <strong>Today</strong>, and that
        is the only box the gate has ever counted.
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
    takeaway: (
      <>
        Use the chat to think. Use <strong>Today</strong> to record. The
        commonest way to lose an evening is to do real work, describe it here,
        and file nothing.
      </>
    ),
  },

  /* 3 ---------------------------------------------------------------- */
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
                What to submit: notes from ONE real conversation — who you spoke
                to, 3 things they said in their own words, what they last did
                about this problem, and what commitment you asked for (and
                whether you got it).
              </p>
              {/* The disclosure's own summary look, not app.proofOfferBtn.
                  That class used to be an underlined accent link and was
                  borrowed here for the shape of one; it is the draft's filled
                  button now, and a mock wearing it would show this line as
                  the loudest control on the slide. */}
              <p className={`${app.proofExamples} ${styles.fakeSummary}`}>
                Show me one that was accepted
              </p>
            </div>
          </Mark>
          <div
            className={`${app.textarea} ${styles.field} ${styles.fieldTall}`}
          >
            Priya, 2nd yr, Block C. Last Tuesday she got back at 22:10, mess was
            shut, paid ₹210 for about ₹90 of food…
          </div>
          <div className={`${app.input} ${styles.ph}`}>Link (optional)</div>
          <div className={styles.fakeAttach}>📎 Attach a screenshot</div>
          <span className={app.primaryBtn}>Submit proof</span>
        </section>

        <section className={app.card}>
          <p className={app.cardLabel}>Today — pushed back</p>
          <Mark n={2}>
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
        What tonight needs, tailored to the task you declared this morning — and
        the phase&apos;s standing ask when the model can&apos;t be reached.
        Don&apos;t know the shape of an accepted answer? That second line
        unfolds a real one. The link and the screenshot under it are optional;
        the words are the proof.
      </>,
      <>
        Pushed back is not a punishment and not a cap. Resubmit: he judges the
        new try against every refused one{" "}
        <em>and the words he refused it with</em>, so the second look can&apos;t
        invent a reason the first didn&apos;t give.
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

  /* 4 ---------------------------------------------------------------- */
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

        {/* Earned, and not yet opened. Going from the refusal straight to an
            advanced stepper skips the one screen the gate exists to produce —
            and which a builder can now sit on, since the card says so rather
            than waiting to be asked. Same builder as the panel above, one
            proof later: the count is met and the bar is full. */}
        <section className={app.card}>
          <p className={app.cardLabel}>3 of 3 — earned</p>
          <div className={app.gateRow}>
            <span>
              <strong>3</strong>/3 proofs toward BUILD
            </span>
          </div>
          <div className={app.gateBar}>
            <div className={app.gateFill} style={{ width: "100%" }} />
          </div>
          <Mark n={3}>
            <p className={app.gateEarned}>Earned. BUILD is yours to open.</p>
            <span className={app.primaryBtn}>Open BUILD</span>
          </Mark>
        </section>
      </>
    ),
    notes: [
      <>
        Counted from proofs stamped with the phase you&apos;re in <em>now</em>.
        A proof already spent on unlocking this phase can&apos;t be spent again.
      </>,
      <>
        The refusal, then the errand. One conversation — not &quot;keep
        validating&quot;. Press the button as often as you like: Django counts
        the rows and answers, and clicking is not evidence.
      </>,
      <>
        Below the bar the button asks and can be refused. At the bar it stops
        asking — the count is already met, so the only thing left is opening
        BUILD, which changes what he&apos;ll talk about. The tech-stack question
        he declined all through VALIDATION is the right question in BUILD.
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
        are about ten minutes of reading, and they credit their sources by name.
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
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)
        return;
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
  const stageClass =
    (s.stage ?? "side") === "stack"
      ? `${styles.stage} ${styles.stageStack}`
      : styles.stage;

  return (
    // One popup for the whole deck, over whichever slide the reader was on:
    // the slide is the argument, and it keeps making it through the blur.
    <SignInProvider behind="the tour">
      <main className={styles.page}>
        <div className={styles.banner}>
          A guided tour of the real product — the screens are the app&apos;s
          own, and the refusals in them are the ones the server actually gives.{" "}
          <SignInButton>Sign in</SignInButton> to get your own Masterji.
        </div>

        <header className={styles.header}>
          <span className={app.brand}>
            Masterji <span className={app.brandHindi}>मास्टरजी</span>
          </span>
          <div className={styles.headerRight}>
            <Changelog />
            <SignInButton className={styles.cta}>Start yours →</SignInButton>
          </div>
        </header>

        <nav className={styles.rail} aria-label="Tour steps" ref={railRef}>
          {SLIDES.map((slide, n) => (
            <button
              key={slide.title}
              className={
                n === i ? styles.stepOn : n < i ? styles.stepPast : styles.step
              }
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
                  s.stage === "stack"
                    ? `${styles.notes} ${styles.notesUnder}`
                    : styles.notes
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
                  className={
                    ex.verdict === "good" ? styles.sampleGood : styles.sampleBad
                  }
                >
                  <span className={styles.sampleLabel}>{ex.label}</span>
                  <p className={styles.sampleText}>{ex.text}</p>
                  {ex.why && <p className={styles.sampleWhy}>{ex.why}</p>}
                </div>
              ))}
            </div>
          )}

          {s.takeaway && <p className={styles.takeaway}>{s.takeaway}</p>}

          {/* The deck used to spend its last slide recapping the day in four
            lines — the same four the landing page already carries, word for
            word. What that slide was actually for is this button, so the
            button is all that survived it. */}
          {last && (
            <div className={styles.finish}>
              <SignInButton className={styles.finishBtn}>
                Start yours →
              </SignInButton>
              <p className={styles.finishNote}>
                One goal, declared tomorrow morning. Sign in with Google —
                nothing to configure.
              </p>
            </div>
          )}
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
    </SignInProvider>
  );
}
