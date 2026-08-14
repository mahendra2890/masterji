/* This app's first service worker, and it does exactly two things.
 *
 * ## Why there is one at all, when lib/manifest.ts says there deliberately
 * isn't
 *
 * That file's reasoning still stands and is not being reversed here. Chrome
 * dropped the service-worker requirement for install-from-menu (108 mobile,
 * 112 desktop), and its stated reason was that sites were shipping empty
 * `fetch` handlers purely to satisfy the check — so shipping one FOR
 * INSTALLABILITY would be the exact anti-pattern Chrome named.
 *
 * Web push does not inherit that conclusion. `pushManager.subscribe()` is
 * reached through a `ServiceWorkerRegistration`, and `push` and
 * `notificationclick` are service-worker events. There is no version of web
 * push without a worker. So this exists because the nudge needs it, and for
 * nothing else.
 *
 * ## NO FETCH HANDLER. NO CACHING. NOT ANY.
 *
 * This is the load-bearing line in the file. A worker that caches anything
 * outlives the deploy that installed it, and an installed PWA whose shell
 * comes from cache is an app pinned to whatever build was live the last time
 * somebody opened it — a bug that reports as "the fix didn't ship" and cannot
 * be fixed by shipping. There is no `fetch` listener below, no `caches.open`,
 * no precache manifest, and no build step that adds one.
 *
 * With no fetch handler the browser goes to the network for every request
 * exactly as it did before this file existed. That is the intended behaviour
 * and it is what makes this worker free: it changes nothing about how the app
 * loads.
 *
 * Offline is a separate feature with a real cost, and if this product ever
 * wants it, it should want it on purpose and in its own pull request — not
 * arrive as a side effect of turning on notifications.
 *
 * ## Deliberately not claiming clients
 *
 * No `skipWaiting`, no `clients.claim`. A worker with no fetch handler has
 * nothing to take over — the only thing an update changes is which script
 * handles the next push, and waiting for the tab to close is fine for that.
 * `skipWaiting` here would buy nothing and is the switch that makes a caching
 * worker dangerous later, so it is not being left lying around.
 */

/* The nudge. The payload arrives encrypted end to end (RFC 8291) and the
 * browser has already decrypted it by the time it lands here — the push
 * service that routed it could not read the builder's task, which is the
 * property that makes it acceptable to put their own words in a notification.
 *
 * `waitUntil` is not optional: without it the browser may kill this worker
 * before showNotification resolves, and Chrome answers a push that showed
 * nothing with its own "This site has been updated in the background" —
 * a notification the product did not write, in a voice that is not Masterji's.
 */
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    /* A push this app did not send, or one from an older payload shape.
       Falls through to the defaults below rather than throwing, because an
       exception here is the same "site updated in the background" notice. */
  }

  const title = data.title || "Still owed tonight";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || "The proof box is still open.",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      /* One tag, so a second notification REPLACES the first rather than
         stacking under it. The server already sends one a day (see
         coach/nudges.py), and this is the second lock on the same promise:
         a retry, a duplicate delivery or a bug upstream costs the builder
         one notification, never a pile of them. */
      tag: "masterji-evening",
      /* And it must not re-buzz to do that replacement. A silent update is
         the honest behaviour when the message has not changed. */
      renotify: false,
      data: { url: data.url || "/" },
    }),
  );
});

/* Tapping it goes to the box it is about — one tap, not two.
 *
 * An already-open tab is focused rather than a second one opened. A builder
 * who has the app open on their phone and taps the nudge should land in the
 * app they already had, with whatever they had typed still in it: this
 * product's proof box holds a draft (lib/drafts.ts), and opening a fresh tab
 * over the top of it is how you lose an evening's typing to a notification.
 */
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/", self.location.origin);

  event.waitUntil(
    (async () => {
      const open = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      for (const client of open) {
        if (new URL(client.url).origin !== target.origin) continue;
        await client.focus();
        /* Only navigate if they are somewhere else in the app. Re-navigating
           a tab that is already on the dashboard would reload it, which is
           the draft-losing move this whole handler is written to avoid. */
        if (new URL(client.url).pathname !== target.pathname) {
          await client.navigate(target.href);
        }
        return;
      }
      await self.clients.openWindow(target.href);
    })(),
  );
});
