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

/** Google's own mark, because a button that says "Continue with Google" and
 * doesn't look like one is asking for more trust than it has earned. This is
 * the moment a stranger hands over an account to a product they met four
 * minutes ago, and the most recognisable thing we can put in front of them is
 * Google's, not ours.
 *
 * It sits on a white chip inside the marigold button: the four-colour mark is
 * specified for light backgrounds, and on marigold it goes muddy. The chip is
 * what keeps the colours correct without giving the popup a white button that
 * belongs to a different product than the one behind it. */
function GoogleG() {
  return (
    <svg viewBox="0 0 48 48" width="18" height="18" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

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
  // Any ?error at all opens it, not only "cancelled". Whoever is holding one
  // came back from Google without a session, and the retry button is inside
  // this popup — so a code this file has no sentence for (a newer one from
  // accounts/oauth.py, say) still lands on the way back in rather than on a
  // landing page that silently forgets the attempt.
  const [open, setOpen] = useState(Boolean(error));
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
        {/* The way out, in the corner people look for one.
            Leaving was already possible — the backdrop asks, and Escape asks
            then closes — but a phone has no Escape key and a backdrop that
            only responds to a tap advertises nothing. So the one screen where
            a stray click costs the signup was also the one screen with no
            visible exit, which is how a careful dialog reads as a trap.
            It asks the same question the backdrop does rather than closing
            outright, and a second press leaves: exactly what Escape does, so
            there is one rule here and not two. */}
        <button
          type="button"
          className={styles.close}
          aria-label="Close sign-in"
          onClick={() => (asking ? leave() : setAsking(true))}
        >
          ×
        </button>
        <p className={styles.wordmark}>मास्टरजी</p>
        <h2 id="sign-in-title" className={styles.title}>
          Sign in to Masterji
        </h2>
        <p className={styles.sub}>
          One goal, earned phases, daily proof — no hiding in planning. Nothing
          to install or configure.
        </p>
        <a className={styles.googleBtn} href={href}>
          <span className={styles.googleChip}>
            <GoogleG />
          </span>
          Continue with Google
        </a>
        {/* What the button actually costs, next to the button.
            The scope requested is "openid email profile" and the callback
            keeps the email, given_name and family_name (accounts/oauth.py) —
            so this is the whole of it, and it is worth a line because the
            reader is about to grant it. If that scope ever widens, this
            sentence is the first thing that has to move. */}
        <p className={styles.scope}>
          Masterji only reads your name and email address.
        </p>
        {error === "cancelled" && (
          <p className={styles.error}>
            Sign-in was cancelled — Masterji will pretend not to notice. Once.
          </p>
        )}
        {/* accounts/oauth.py sends this when the sign-in that came back is not
            one this browser started: the ten-minute window ran out at Google's
            account picker, or the cookie holding the other half went away
            mid-flow. Both want the button above, so say so and get out of the
            way. */}
        {error === "expired" && (
          <p className={styles.error}>
            That sign-in took too long to come back. One more press and
            you&rsquo;re in.
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
