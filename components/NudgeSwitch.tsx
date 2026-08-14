"use client";

import { useEffect, useState } from "react";
import styles from "@/app/masterji.module.css";
import { getPushConfig } from "@/lib/coach-api";
import {
  currentState,
  disable,
  enable,
  iosNeedsInstall,
  supported,
  type PushState,
} from "@/lib/push";

/** The evening nudge's on/off, in one line at the foot of the Today card.
 *
 * ## Why it is here and not in the control row
 *
 * Both control rows in Masterji.tsx carry a comment saying they are at their
 * limit, and the second one was measured at 320px of 320px before the language
 * switch was moved out of it. A sixth control would put them back on three
 * lines. More than that, the row is account chrome — sign out, the changelog,
 * delete account — and this is not a setting about the account. It is a
 * setting about tonight's box, which is what this card is.
 *
 * So it sits under the thing it is about, where the sentence explains itself
 * without a caption or a disclosure, and the row stays a row of controls.
 *
 * ## Why every state gets words
 *
 * The most likely way this feature lies to a builder is a control that reads
 * "on" for a browser that has quietly refused. `blocked` is the case that
 * matters: once a browser is told no, no API can ask again, so a button that
 * offers to turn nudges on is a button that cannot work. It says where the
 * switch actually is instead. And on iOS, where web push exists only from a
 * home-screen install, "your browser can't" would be false — the honest
 * answer names the two taps that make it possible.
 *
 * Nothing here asks for permission on mount. The prompt is spent on a press,
 * once, after the builder has read what it is for.
 */
export default function NudgeSwitch() {
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [evening, setEvening] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    (async () => {
      if (!supported()) {
        if (live) setState("unsupported");
        return;
      }
      // The deployment's answer first. With no VAPID keys set this feature is
      // off end to end (see backend/config/settings.py), and the right thing
      // to draw then is nothing at all rather than a switch that would 503.
      const config = await getPushConfig().catch(() => null);
      if (!live) return;
      if (!config?.configured) {
        setState(null);
        return;
      }
      setEvening(config.eveningFrom);
      setState(await currentState());
    })();
    return () => {
      live = false;
    };
  }, []);

  if (state === null) return null;

  // Nothing to offer and nothing to explain — this browser will not do it and
  // no press changes that. The one exception is iOS in a tab, which is a
  // browser that WILL, after two taps the builder can make right now.
  if (state === "unsupported") {
    return iosNeedsInstall() ? (
      <p className={styles.nudgeNote}>
        Want a nudge if this is still empty tonight? On iPhone that needs the
        app on your home screen first — Share, then Add to Home Screen.
      </p>
    ) : null;
  }

  if (state === "blocked") {
    return (
      <p className={styles.nudgeNote}>
        Notifications are switched off for this site in your browser&apos;s
        settings. That&apos;s the only place it can be switched back on.
      </p>
    );
  }

  async function toggle() {
    setBusy(true);
    setFailed(false);
    try {
      setState(state === "on" ? await disable() : await enable());
    } catch {
      // Said out loud. A switch that silently fails to turn on is worse than
      // one that says it couldn't: the builder walks away believing they will
      // be reminded, and finds out by missing an evening.
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className={styles.nudgeSwitch} onClick={toggle} disabled={busy}>
        {busy
          ? "…"
          : state === "on"
            ? "Nudge me tonight: on — turn it off"
            : evening
              ? `Nudge me after ${hour(evening)} if this is still empty`
              : "Nudge me tonight if this is still empty"}
      </button>
      {failed && (
        <p className={styles.nudgeNote}>
          {state === "on"
            ? "Couldn't turn that off — try again."
            : "Couldn't set that up — try again."}
        </p>
      )}
    </>
  );
}

/** 17 → "5pm". The server names the hour it starts looking, and a builder
 * reading "17" has to do the conversion the copy should have done. */
function hour(h: number): string {
  const suffix = h < 12 ? "am" : "pm";
  const twelve = h % 12 === 0 ? 12 : h % 12;
  return `${twelve}${suffix}`;
}
