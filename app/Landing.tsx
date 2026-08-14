// What a stranger sees at "/", and where everyone signs in.
//
// Until recently there was nothing here: "/" mounted the app, the app asked
// who you were, and anyone who wasn't anybody got replaced by /login/ — a
// wordmark, one sentence and a Google button. Every reason to want this
// product lived in the README. So a visitor was asked for an account before
// being shown a single thing the account would do.
//
// /login/ is now gone entirely. It had nothing this page doesn't: once "/"
// could talk, a sign-in page was a detour that answered a click on "Sign in"
// by asking the visitor to click "Sign in" again. Its contents live in a popup
// over this one now (components/SignIn.tsx), so the argument a reader was
// halfway through stays on screen, blurred, while they make the account.
//
// Deliberately short, and the tour at /demo/ is shorter — it is a bridge to
// the button, not a manual. This page states the shape of the thing; the tour
// shows the four screens a visitor needs to see before handing over a Google
// account. Anything true of the product but only useful once you're inside it
// belongs in neither.
//
// A server component: no hooks, no auth call, no spinner. The words are in
// the HTML that comes down the wire, which also means a crawler and a link
// preview finally have something to read.

import Link from "next/link";
import Changelog from "@/components/Changelog";
import { SignInButton, SignInProvider } from "@/components/SignIn";
import app from "./masterji.module.css";
import styles from "./landing.module.css";

/** The day, in the product's own order. This is the only copy of it now: the
 * tour used to close on a recap of the same four lines, kept word-for-word,
 * and two descriptions of one loop is exactly the kind of thing that drifts.
 * The tour teaches the screens; this states the shape. */
const LOOP = [
  {
    when: "Morning",
    what: "Declare one task under Today. Ten seconds. He tells you if it's the wrong week's work.",
  },
  {
    when: "During",
    // Credit first, gate second. This was the last place in the product still
    // leading with "the chat records nothing" — the same sentence was fixed in
    // the composer note, the welcome message and the tour, and this copy got
    // missed. Leading with the gate reads as "don't bother typing", and since
    // suggest_proof shipped it is also half untrue: the chat is where the
    // evening's proof is written FROM, even though Today is where it lands.
    // Same words, same rule, second clause.
    what: "Do it. Think out loud with him when you're stuck — he writes tonight's proof from what you tell him. Nothing counts until you file it.",
  },
  {
    when: "Evening",
    what: "File the proof under Today. If he drafted it from your conversation, that's one tap.",
  },
  {
    when: "When the proofs are in",
    what: "The gate opens the next phase. Not before, however well you argue.",
  },
];

export default function Landing({
  /** Why the last sign-in attempt didn't take, when it didn't. Django's OAuth
   * callback puts it here on its way back from Google. */
  error,
  /** Where to land after Google. Already checked to be a same-site path by
   * page.tsx — it goes into an href below. */
  next = "/",
}: {
  error?: string;
  next?: string;
}) {
  return (
    // The provider owns the one popup for this screen and hands every trigger
    // below the same opener. It's a client component wrapping server-rendered
    // children, so none of the words on this page cross into the bundle.
    <SignInProvider behind="the home page" error={error} next={next} offerDemo>
      <main className={styles.page}>
        <header className={styles.top}>
          <span className={styles.brand}>
            Masterji <span className={styles.brandHindi}>मास्टरजी</span>
          </span>
          <div className={styles.topRight}>
            <Changelog />
            <SignInButton className={styles.topLink}>Sign in</SignInButton>
          </div>
        </header>

        {/* No second मास्टरजी here — the header carries it four lines up, and a
          wordmark repeated inside its own hero reads as a template rather
          than as a signature. */}
        <section className={styles.hero}>
          <h1 className={styles.title}>The coach who makes you ship.</h1>
          {/* Who it's for, before what it does — and the first thing on this
            page that was missing entirely.

            Every reason to want this product named a mechanism: one goal, four
            phases, a server that won't open the next one. None of it said whose
            problem that solves. The audience was only ever implied, by the
            examples — a tiffin app, the Block C mess queue, Instagram
            resellers — and an implication is not a statement: a reader who
            doesn't recognise themselves in a mess queue has been told nothing.

            The long version, with the numbers under it, is in the README (GUESSS
            India 2023: 32.5% of college students nascent entrepreneurs, ~4.8% of
            student ventures ever making revenue). A landing page gets one
            sentence, so it spends it on the person rather than the statistic —
            and on the specific thing they are stuck with, which is not a lack of
            information. They have the plans and the tutorials. What they don't
            have is anyone who will ask to see it. */}
          <p className={styles.sub}>
            For first-time builders in India who never got a mentor — the plans
            are made, the tutorials are watched, and nobody is waiting to see it
            on Friday. One goal. Four phases you have to earn. A task declared
            every morning, proof filed every evening — and a server that will not
            open the next phase until the evidence is actually in.
          </p>
          <div className={styles.actions}>
            <SignInButton className={styles.primary}>
              Start free with Google
            </SignInButton>
            <Link className={styles.secondary} href="/demo/">
              See how it works — no sign-in
            </Link>
          </div>
          <p className={styles.reassure}>
            Free. One goal at a time. Nothing to install or configure.
          </p>
        </section>

        {/* The product, standing still — and the first thing on this page that
          isn't an assertion.
          Everything above and below is words about a coach nobody has met. A
          visitor was asked for a Google account having been shown nothing at
          all: the tour was the only place the screens existed, and it costs a
          click most people don't spend. One frame here is what that click was
          for.
          Every class in it comes from masterji.module.css — the app's own
          screens, the way the tour builds its mocks. Not a second sales page
          about the product: a crop of it, with the voice in it, because the
          voice is the thing being sold.
          Deliberately still no proof counts. They live in gates.py and are
          quoted, under a copy rule, by the tour; the bar below has a fill and
          no fraction over it, which promises nothing that a change to
          PROOFS_REQUIRED could turn into a lie. */}
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>This is the whole app</h2>
          <p className={styles.sectionBody}>
            Two cards and a conversation. Nothing to set up, no projects, no
            board — the screen below is what you get on day one and what you
            get on day ninety.
          </p>

          <div className={styles.shot}>
            <div className={styles.shotCards}>
              <section className={app.card}>
                <p className={app.cardLabel}>The goal</p>
                <h3 className={app.goalTitle}>
                  Tiffin-delivery app for my college
                </h3>
                <ol className={app.stepper}>
                  <li className={app.stepDone}>IDEA</li>
                  <li className={app.stepNow}>VALIDATION</li>
                  <li className={app.stepTodo}>BUILD</li>
                  <li className={app.stepTodo}>LAUNCH</li>
                  <li className={app.stepTodo}>TRACTION</li>
                </ol>
                {/* Word for word what the server serves a builder standing
                    where this card says they are. The bar below reads 2 of 3,
                    and VALIDATION's ask moves with the count
                    (guidance.BEATS) — so the honest line here is the third
                    rung's, not the phase's constant. It used to be
                    PHASE_HINT[VALIDATION], which is now what a builder reads
                    only once all three conversations are in. */}
                <p className={app.phaseHint}>
                  Third conversation. Ask for something that costs them — an
                  hour, an intro, money.
                </p>
                <div className={app.gateBar}>
                  <div className={app.gateFill} style={{ width: "66%" }} />
                </div>
              </section>

              <section className={app.card}>
                <p className={app.cardLabel}>Today</p>
                <p className={app.declared}>
                  Declared:{" "}
                  <em>Interview the mess aunty about the 9pm rush</em>
                </p>
                <p className={app.accepted}>
                  ✓ accepted — Ramesh gave you a number and an intro to Block
                  B. That&apos;s a conversation, not a survey.
                </p>
              </section>
            </div>

            {/* Both sides of it. A single reply with nobody to reply to is a
              quote, and it leaves the column half empty — which is the exact
              complaint this frame would otherwise be advertising. The question
              is also the one that makes the answer worth reading: it is the
              thing every first-time builder wants to talk about, and the phase
              he is in is why he isn't allowed to. */}
            <div className={styles.shotChat}>
              <div className={app.messages}>
                <div className={app.userMsg}>
                  <p className={app.msgBody}>
                    Quick one — should I build this in Next.js or Remix? And
                    Postgres or Mongo?
                  </p>
                </div>
                <div className={app.coachMsg}>
                  <span className={app.avatar}>म</span>
                  <p className={app.msgBody}>
                    Fair question, wrong week. Both of those are BUILD&apos;s
                    problem, and neither answer survives a user you haven&apos;t
                    met. The Mom Test says talk about their life, not your idea
                    — go ask the mess aunty what she does when orders pile up.
                    Bring me notes tonight.
                  </p>
                </div>
                {/* The second objection, and the commoner one: the page used
                  to answer only the builder who already has an idea, which is
                  not the visitor most likely to leave. The builder's line is
                  guidance.WORKSHOP_OPENERS[0] word for word — a real tappable
                  chip, not copy written for this page. Every claim in the
                  reply is server truth: WORKSHOP_TURNS is 15, the pile is
                  capped at three (models.Workshop), the room grades nothing
                  and banks nothing, and suggest_goal fills the commit box
                  while pressing it stays the builder's. */}
                <div className={app.userMsg}>
                  <p className={app.msgBody}>I don&apos;t have an idea yet.</p>
                </div>
                <div className={app.coachMsg}>
                  <span className={app.avatar}>म</span>
                  <p className={app.msgBody}>
                    Then we start before the ladder. Fifteen turns, and the
                    first one is yours: what did you stand in a queue for this
                    week, or watch somebody work around? Park up to three, pick
                    one. Nothing in here is graded and nothing banks — when one
                    of them wins I&apos;ll fill the commit box, and pressing it
                    is still yours.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>A day with Masterji</h2>
          <ol className={styles.loop}>
            {LOOP.map((step) => (
              <li key={step.when} className={styles.loopStep}>
                <p className={styles.loopWhen}>{step.when}</p>
                <p className={styles.loopWhat}>{step.what}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>
            You don&apos;t get to skip a phase
          </h2>
          {/* No proof counts printed here on purpose. They live in
            backend/coach/gates.py and are quoted, under a copy rule, by the
            tour — a second copy on a marketing page is a promise nothing
            keeps the day one of them changes. */}
          <ol className={styles.phases}>
            <li className={styles.phase}>IDEA</li>
            <li className={styles.phase}>VALIDATION</li>
            <li className={styles.phase}>BUILD</li>
            <li className={styles.phase}>LAUNCH</li>
            <li className={styles.phase}>TRACTION</li>
          </ol>
          {/* The ladder starts at IDEA and the product doesn't: there is a
            room before it, and this page said nothing about it for a day. The
            first screen is not commit-or-leave, which is the thing a visitor
            with no idea yet has to know before the ladder above reads as a
            door rather than a wall. Fifteen turns is WORKSHOP_TURNS; the room
            is not on this list because it is not a phase — nothing in it
            banks, and gates.py never reads it.

            Named, and placed, in the words the product itself uses: Tour.tsx
            says "the workshop is under the box" and Masterji.tsx says
            "Workshop closed." when the turns run out. A visitor told about an
            unnamed room has to recognise it on arrival; one told its name and
            where it sits does not. */}
          <p className={styles.sectionBody}>
            Before IDEA there&apos;s a room that isn&apos;t on this ladder — the
            workshop, under the commit box: fifteen turns to find the idea, if
            you don&apos;t have one yet. Nothing in it counts toward anything —
            that&apos;s the point of it.
          </p>
          <p className={styles.sectionBody}>
            Each phase opens on evidence you banked in the phase before it. The
            coach can be argued with; the gate can&apos;t — it&apos;s a{" "}
            <code>WHERE</code> clause, and the model only gets to{" "}
            {/* The explicit {" "} is load-bearing: a text node that starts on
              its own source line loses its leading space in the build, so
              "</em> an advance" shipped as "proposean advance" and only the
              compiled output ever showed it. Same reason the Google button's
              label uses a flex gap rather than a space. */}
            <em>propose</em>{" "}
            an advance. Talk about tech stacks all you like in VALIDATION. It
            won&apos;t count, and he&apos;ll say so.
          </p>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Why trust this coach?</h2>
          <p className={styles.sectionBody}>
            Not on anyone&apos;s track record. Masterji makes no claim to
            founder wisdom — be suspicious of any tool that does. Its authority
            is procedural: the method is borrowed in the open from{" "}
            <em>The Mom Test</em>, <em>The Lean Startup</em> and <em>MAKE</em>,
            and every refusal it makes traces to a condition you can read in{" "}
            <a
              className={styles.link}
              href="https://github.com/mahendra2890/masterji/blob/main/backend/coach/gates.py"
              target="_blank"
              rel="noreferrer"
            >
              gates.py
            </a>{" "}
            and a test that pins it. A referee doesn&apos;t need to be a better
            player than the players.
          </p>
        </section>

        <section className={styles.close}>
          <h2 className={styles.closeTitle}>
            One goal, declared tomorrow morning.
          </h2>
          <div className={styles.actions}>
            <SignInButton className={styles.primary}>
              Start free with Google
            </SignInButton>
            <Link className={styles.secondary} href="/demo/">
              See how it works — no sign-in
            </Link>
          </div>
        </section>

        <footer className={styles.foot}>
          <a
            className={styles.link}
            href="https://github.com/mahendra2890/masterji"
            target="_blank"
            rel="noreferrer"
          >
            Source
          </a>
          <span className={styles.footDim}>
            Built for the bestpossible.ai Build Season 2026
          </span>
        </footer>
      </main>
    </SignInProvider>
  );
}
