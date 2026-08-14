"use client";

/* The browser half of the evening nudge (#87).
 *
 * Four states, and every one of them has to be drawable, because the failure
 * this module is most likely to produce is a control that says "on" for a
 * builder whose browser has quietly refused:
 *
 *   unsupported  — no service worker, no PushManager, or an iOS home screen
 *                  that hasn't been installed yet (see IOS_NEEDS_INSTALL)
 *   off          — supported, nothing granted, nothing subscribed
 *   on           — permission granted AND a subscription the server holds
 *   blocked      — the builder said no, and only their browser settings can
 *                  change that. Nothing this app draws can undo it, so it
 *                  must not offer to.
 *
 * Permission is asked for exactly once, on a press, and never on load. A page
 * that asks on mount spends the one grant a browser gives before the builder
 * knows what it is for — and once denied there is no second ask, ever.
 */

import { dropPushSubscription, getPushConfig, savePushSubscription } from "./coach-api";
import { decodeKey } from "./vapid";

export type PushState = "unsupported" | "off" | "on" | "blocked";

/** Registered lazily, from the press — not on mount.
 *
 * The worker exists only to receive pushes (see public/sw.js: no fetch
 * handler, no caching), so there is nothing to gain from installing it on
 * every visit for the builders who never turn nudges on. It also keeps the
 * registration honestly paired with the thing that needs it: if this call
 * ever disappears, so does the only worker this app has.
 */
async function worker(): Promise<ServiceWorkerRegistration> {
  const existing = await navigator.serviceWorker.getRegistration("/");
  return existing ?? navigator.serviceWorker.register("/sw.js", { scope: "/" });
}

export function supported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** Whether this browser is one where the answer is "install it first".
 *
 * Safari has supported web push since 16.4 and supports it ONLY from a home
 * screen install — in a Safari tab, `PushManager` is not there at all. That
 * reads identically to a browser that will never support it, and the two need
 * opposite things said to them: one is "your browser can't", the other is
 * "Share → Add to Home Screen, then come back", which is a thing the builder
 * can act on today.
 *
 * `standalone` is the iOS-only signal for "running from the home screen". If
 * it exists and is false, this is a tab on iOS.
 */
export function iosNeedsInstall(): boolean {
  if (typeof window === "undefined" || "PushManager" in window) return false;
  const standalone = (navigator as { standalone?: boolean }).standalone;
  return standalone === false;
}

export async function currentState(): Promise<PushState> {
  if (!supported()) return "unsupported";
  if (Notification.permission === "denied") return "blocked";
  if (Notification.permission !== "granted") return "off";
  // Granted is not subscribed. A builder can grant permission and then have
  // the subscription dropped underneath them — clearing site data, a browser
  // profile reset, or the push service retiring the endpoint — and a control
  // that reads permission alone would say "on" for a device the server has no
  // way to reach.
  const registration = await navigator.serviceWorker.getRegistration("/");
  const subscription = await registration?.pushManager.getSubscription();
  return subscription ? "on" : "off";
}

/** Turn it on. Returns the state the control should now draw.
 *
 * Throws only for something the builder should be told about — the server
 * refusing the subscription, or the push service failing. A denied permission
 * is not an error: it is an answer, and it comes back as "blocked".
 */
export async function enable(): Promise<PushState> {
  if (!supported()) return "unsupported";
  const config = await getPushConfig();
  if (!config.configured || !config.publicKey) return "unsupported";

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    return permission === "denied" ? "blocked" : "off";
  }

  const registration = await worker();
  // `ready` and not the registration alone: a worker that has just been
  // registered is still installing, and pushManager on an installing worker
  // rejects. This resolves when one is active.
  await navigator.serviceWorker.ready;

  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({
      // Not optional and not a default. Chrome refuses a subscription without
      // it, because a push a site cannot be identified as the sender of is a
      // push nobody can rate-limit or block.
      userVisibleOnly: true,
      applicationServerKey: decodeKey(config.publicKey),
    }));

  const json = subscription.toJSON();
  await savePushSubscription({
    endpoint: subscription.endpoint,
    keys: {
      p256dh: json.keys?.p256dh ?? "",
      auth: json.keys?.auth ?? "",
    },
    // The zone this browser is in, which is the whole reason the server can
    // know when this builder's evening has started. Everything else in this
    // app sends a local DATE; a nudge has no request to read one from, so
    // this is the one place the zone itself is handed over.
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  });
  return "on";
}

/** Turn it off, from both ends.
 *
 * The server row goes first. If unsubscribing locally fails after that, the
 * builder is left with a dead subscription their browser still lists and a
 * server that will never push to it — annoying. The other order leaves a
 * server that pushes to a device the builder has just switched off, which is
 * the failure that matters.
 *
 * Notification permission is deliberately NOT revoked; no API can, and the
 * builder keeping a grant they may want again next week is the right default.
 */
export async function disable(): Promise<PushState> {
  if (!supported()) return "unsupported";
  const registration = await navigator.serviceWorker.getRegistration("/");
  const subscription = await registration?.pushManager.getSubscription();
  await dropPushSubscription(subscription?.endpoint);
  await subscription?.unsubscribe().catch(() => false);
  return "off";
}
