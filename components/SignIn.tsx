"use client";

// Signing in, as a popup over whatever you were reading.
//
// There used to be a /login/ page. It held a wordmark, one sentence and a
// Google button, and every route into it was a button that already said "Start
// free with Google" — so the reward for deciding was a second page asking you
// to decide again. The page is gone; this is what its contents became.
//
// A popup rather than a redirect because the screen behind it is the argument.
// A visitor three slides into the tour, or halfway down the landing page, is
// mid-thought; replacing that with a bare sign-in page threw the argument away
// at the exact moment it was working. Blurred and still there, it keeps making
// its case while the account gets made.
//
// Leaving is a question, not an accident. A click on the backdrop of a normal
// modal dismisses it, which is fine for a filter panel and wrong for the one
// screen where a stray click costs the signup — so the backdrop asks, and both
// answers are spelled out. Escape asks the same question once, then closes on a
// second press, because a dialog nobody can escape from is its own bug.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import DevLogin from "./DevLogin";
import styles from "./sign-in.module.css";

type SignIn = {
  /** Put the popup up. */
  open: () => void;
  /** Where the popup's button goes, and where a trigger goes without
   * JavaScript: straight to Django, which redirects to Google's picker. */
  href: string;
};

const Ctx = createContext<SignIn | null>(null);

/** Wraps a screen that can sign someone in, and owns the one popup for it.
 *
 * `children` is whatever was on screen — server-rendered nodes included; this
 * component only adds the dialog beside them. */
export function SignInProvider({
  children,
  /** What the reader goes back to, named, for the question the backdrop asks.
   * "the tour", "the home page" — it lands in a sentence. */
  behind,
  /** Why the last attempt didn't take, if it didn't. Its presence also opens
   * the popup on arrival: whoever is holding it just came back from Google
   * without a session, and the retry button is in here. */
  error,
  /** Where to land after Google. Checked by the caller — it goes into an
   * href. */
  next = "/",
  /** Offer the tour as an alternative. True on the landing page, false in the
   * tour itself, where it would point at the page it is covering. */
  offerDemo = false,
}: {
  children: ReactNode;
  behind: string;
  error?: string;
  next?: string;
  offerDemo?: boolean;
}) {
  const [open, setOpen] = useState(error === "cancelled");
  const value = useRef<SignIn>({
    open: () => setOpen(true),
    href: `/api/auth/google/login/?next=${encodeURIComponent(next)}`,
  });

  return (
    <Ctx.Provider value={value.current}>
      {children}
      <SignInDialog
        open={open}
        onClosed={() => setOpen(false)}
        href={value.current.href}
        behind={behind}
        error={error}
        offerDemo={offerDemo}
      />
    </Ctx.Provider>
  );
}

/** A link that opens the popup, and is a real link to Google if the click
 * never reaches React — no JavaScript, or a middle-click into a new tab. */
export function SignInButton({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  const signIn = useContext(Ctx);

  return (
    <a
      className={className}
      href={signIn?.href ?? "/api/auth/google/login/?next=%2F"}
      onClick={(e) => {
        // Let the browser have the clicks that mean "somewhere else, not
        // here": a new tab or window is not a request for a popup.
        if (!signIn || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        signIn.open();
      }}
    >
      {children}
    </a>
  );
}

function SignInDialog({
  open,
  onClosed,
  href,
  behind,
  error,
  offerDemo,
}: {
  open: boolean;
  onClosed: () => void;
  href: string;
  behind: string;
  error?: string;
  offerDemo: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  // Whether the backdrop's question is on screen. Reset every time the popup
  // goes away, so a reader who left and came back isn't met by it.
  const [asking, setAsking] = useState(false);
  const stayRef = useRef<HTMLButtonElement>(null);

  // showModal() is what makes it modal — the backdrop, the focus trap and the
  // inertness of the page behind are all its doing, and none of them come from
  // the open attribute alone. So the element renders closed on the server and
  // is opened here.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
    if (!open) setAsking(false);
  }, [open]);

  // The question is the new thing on screen, so it takes the focus — and
  // "Stay here" rather than "Go back", because a blind press of the space bar
  // should not be what loses the signup.
  useEffect(() => {
    if (asking) stayRef.current?.focus();
  }, [asking]);

  const leave = useCallback(() => {
    setAsking(false);
    ref.current?.close();
  }, []);

  return (
    <dialog
      ref={ref}
      className={styles.dialog}
      aria-labelledby="sign-in-title"
      // A click that lands on the dialog element itself landed on the backdrop:
      // everything visible is inside the panel below.
      onClick={(e) => {
        if (e.target === ref.current) setAsking(true);
      }}
      // Escape asks the same question the backdrop does, then closes on a
      // second press — so the popup is always escapable, which a dialog that
      // can only be dismissed by hitting the right button is not.
      //
      // Both presses are handled here, and the platform is left out of it. The
      // dialog's own cancel event is the obvious place for the first press and
      // does not work: Chrome routes Escape through a close watcher that closed
      // the popup regardless of preventDefault() on cancel. Preventing the
      // keydown does hold it shut — but then the watcher will not fire again
      // for the second press either (both verified in Chrome). Owning the key
      // outright is the only version that behaves the same twice.
      //
      // A platform close request that isn't a keypress — Android's back
      // gesture, say — still closes, and should: that one means "back" plainly
      // enough that asking would be answering a question nobody asked.
      onKeyDown={(e) => {
        if (e.key !== "Escape") return;
        e.preventDefault();
        if (asking) leave();
        else setAsking(true);
      }}
      onClose={onClosed}
    >
      <div className={styles.panel}>
        <p className={styles.wordmark}>मास्टरजी</p>
        <h2 id="sign-in-title" className={styles.title}>
          Sign in to Masterji
        </h2>
        <p className={styles.sub}>
          One goal, earned phases, daily proof — no hiding in planning. Nothing
          to install or configure.
        </p>
        <a className={styles.googleBtn} href={href}>
          Continue with Google
        </a>
        {error === "cancelled" && (
          <p className={styles.error}>
            Sign-in was cancelled — Masterji will pretend not to notice. Once.
          </p>
        )}
        {offerDemo && (
          <a className={styles.back} href="/demo/">
            or watch the demo first →
          </a>
        )}
        <DevLogin />

        {asking && (
          <div
            className={styles.ask}
            role="group"
            aria-label="Leave sign-in without signing in?"
          >
            <p className={styles.askQ}>
              Go back to {behind}? Nothing is lost — the same button brings this
              back.
            </p>
            <div className={styles.askActions}>
              <button
                ref={stayRef}
                className={styles.stayBtn}
                onClick={() => setAsking(false)}
              >
                Stay here
              </button>
              <button className={styles.leaveBtn} onClick={leave}>
                Go back
              </button>
            </div>
          </div>
        )}
      </div>
    </dialog>
  );
}
