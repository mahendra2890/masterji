// The dashboard's frame, drawn before anyone knows whose dashboard it is.
//
// No "use client" and no hooks, so this renders on the server: it is what a
// returning builder's browser paints straight out of the HTML, while the JS is
// still downloading and Django has not yet been asked who they are. Before
// this existed, `firstPaint="app"` painted nothing at all — 39 visible
// characters of document, the <title> and no more — and the first pixel of the
// product waited on ~200KB gzip of JS, hydration and a round trip to a Render
// free instance (#239).
//
// It is deliberately the frame and not a guess at the contents. Every piece of
// text in here is structural — the wordmark, the two pane names, the two card
// labels — and true of every builder's dashboard. Nothing is invented from a
// cookie that was never validated.
//
// Rendered from two places, and that is the point rather than a coincidence:
// AuthGate paints it while it asks Django who you are, and Masterji paints the
// same component while it fetches the coach state. One <main class=app> stands
// still from the first paint to the last, which is what took CLS on this route
// from 0.0625 to nothing — see the note on `.loading`'s removal in
// masterji.module.css (#241).
//
// The one case it guesses wrong: a builder with no active goal gets the
// onboarding screen, which is a different layout entirely, so they see this
// frame and then a full swap. That is the same bet `firstPaint` already makes
// from the cookie, and it is the minority case — a returning builder, the
// population this exists for, has a goal.

import styles from "./masterji.module.css";

/** One grey bar. `w` is a length, because these stand in for words and a word
 * has a width; heights come from the classes below so they stay tied to the
 * real rules they are standing in for. */
function Bar({ w, className }: { w: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`${styles.shellBar} ${className ?? ""}`}
      style={{ width: w }}
    />
  );
}

/** A control's worth of space, sized by .linkBtn — the same 44px rule the
 * links and buttons it stands in for are laid out by, so these rows are the
 * height they will become rather than a number copied out of one. */
function Action({ w }: { w: string }) {
  return (
    <span aria-hidden="true" className={styles.linkBtn}>
      <span className={styles.shellBar} style={{ width: w }} />
    </span>
  );
}

export default function DashboardShell() {
  return (
    // aria-busy rather than aria-hidden: this is the page, provisionally, and
    // a screen reader should be told it is still settling rather than told
    // there is nothing here.
    <main className={styles.app} data-pane="today" aria-busy="true">
      <header className={styles.header}>
        {/* Real, and identical to the header it becomes. The wordmark is not a
            guess about anybody. */}
        <span className={styles.brand}>
          Masterji <span className={styles.brandHindi}>मास्टरजी</span>
        </span>
        {/* The header's height, taken from the rule that actually sets it
            rather than from a number copied out of one. The language switch is
            the tallest thing in this row, and it is structural — both options
            exist on every dashboard — so this is the real control's geometry
            with the one data-dependent part left out: which of the two is lit
            is the answer we are still waiting for, so neither is.

            A direct child of .header on purpose. `.header > .toneSwitch` takes
            margin-left: auto, and a placeholder one level down would sit in a
            different place than the control it stands in for. */}
        <div className={styles.toneSwitch} aria-hidden="true">
          <span className={styles.toneOpt}>EN</span>
          <span className={styles.toneOpt} lang="hi">
            हिं
          </span>
        </div>
        <div className={styles.headerRight}>
          {/* The username. .who is the class that hides it below 820px, so
              wearing it means this row wraps on a phone exactly as the real
              one does instead of standing in for a control that is not
              there. */}
          <span className={styles.who} aria-hidden="true">
            <Bar w="72px" />
          </span>
          <Bar w="76px" className={styles.shellWord} />
          <Bar w="67px" className={styles.shellWord} />
          {/* "sign out" is the one control in this row the mobile block gives
              a 44px target, so it is what sets .headerRight's height there:
              31px on a laptop and 44px on a phone. An empty one is that box,
              on both, without either number appearing here. */}
          <span aria-hidden="true" className={styles.signOut} />
        </div>
      </header>

      {/* Phone only — display:none above 820px. Both panes always exist and
          "today" is the one Masterji opens on, so this is exact rather than a
          placeholder, and the sticky row does not appear from nowhere and push
          the columns down on the device where it is on screen.

          Buttons rather than spans
          because a button's line box is not a span's: at 390px the same
          classes on a span came out 50px tall against the real row's 45, and
          the 5px landed on everything below it. Disabled, so the row is the
          shape it will be without being a control that does nothing. */}
      <nav className={styles.panes} aria-hidden="true">
        <button type="button" disabled className={styles.paneOn}>
          Today
        </button>
        <button type="button" disabled className={styles.pane}>
          Masterji
        </button>
      </nav>

      <div className={styles.columns}>
        <aside className={styles.side}>
          <section className={styles.card}>
            <p className={styles.cardLabel}>The goal</p>
            <Bar w="100%" className={styles.shellTitle} />
            <Bar w="62%" className={styles.shellTitle} />
            <Bar w="100%" className={styles.shellStepper} />
            <Bar w="88%" className={styles.shellLine} />
            <Bar w="54%" className={styles.shellLine} />
            <Bar w="100%" className={styles.shellMeter} />
            {/* The two rows of exits under the meter — the phase request, then
                "not sure about this one? / close this goal". Reserved because
                they are 88px of the card and the card is what fills in around
                them. */}
            <div>
              <Action w="140px" />
            </div>
            <div>
              <Action w="118px" />
              <Action w="88px" />
            </div>
          </section>

          <section className={styles.card}>
            <p className={styles.cardLabel}>Today</p>
            <Bar w="58%" className={styles.shellLine} />
            <Bar w="100%" className={styles.shellBox} />
            <div>
              <Action w="96px" />
            </div>
          </section>
        </aside>

        {/* The chat pane's height is the grid row's, not its content's, so
            messages landing inside it later move nothing. The two bars are
            here so the largest box on the screen does not read as an empty
            bordered rectangle while it waits. */}
        <section className={styles.chat}>
          <div className={styles.messages}>
            <Bar w="76%" className={styles.shellMsg} />
            <Bar w="54%" className={styles.shellMsg} />
          </div>
        </section>
      </div>
    </main>
  );
}
