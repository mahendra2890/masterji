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
    what: "Do it. Think out loud with him when you're stuck — and remember the chat records nothing.",
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
          <p className={styles.sub}>
            One goal. Four phases you have to earn. A task declared every
            morning, proof filed every evening — and a server that will not open
            the next phase until the evidence is actually in.
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
          </ol>
          <p className={styles.sectionBody}>
            Each one opens on evidence you banked in the phase before it. The
            coach can be argued with; the gate can&apos;t — it&apos;s a{" "}
            <code>WHERE</code> clause, and the model only gets to{" "}
            <em>propose</em> an advance. Talk about tech stacks all you like in
            VALIDATION. It won&apos;t count, and he&apos;ll say so.
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
