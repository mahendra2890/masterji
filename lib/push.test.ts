import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { decodeKey } from "./vapid";

const SOURCE = readFileSync(join(__dirname, "..", "public", "sw.js"), "utf8");

/** The worker with its comments taken out.
 *
 * Necessary rather than fussy: that file's header explains at length why it
 * has no `fetch` handler, no `caches.open` and no `skipWaiting`, so a test
 * matched against the raw text fails on the prose that promises the very
 * thing it is checking for — and the obvious fix, rewording the comments so
 * they never name what they forbid, would trade the file's whole explanation
 * for a passing test. Strip them instead and assert against the code. */
const WORKER = SOURCE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* The comment at the top of public/sw.js says this worker must never cache
   anything, and a comment is not a guarantee. These are.

   The failure being prevented is not hypothetical and it is not recoverable
   by shipping: a service worker with a fetch handler and a cache outlives the
   deploy that installed it, so an installed PWA serves whatever shell was
   live the last time it was opened. It reports as "the fix didn't go out",
   every check passes, and the only cure is code that is already on the
   builder's phone.

   Read as text rather than executed because what is being asserted is what
   the FILE contains — a worker that only registers a fetch handler on some
   branch would still be a caching worker, and running it would find that only
   if the test happened to take that branch. */
describe("the service worker", () => {
  it("registers no fetch handler", () => {
    expect(WORKER).not.toMatch(/addEventListener\(\s*["'`]fetch/);
    expect(WORKER).not.toMatch(/\bonfetch\b/);
  });

  it("touches no cache, by any route", () => {
    /* `caches` is the whole Cache Storage API, and there is no way to cache a
       response without it. Matched as a word so the prose above — which uses
       "caching" and "precache" to explain why none of this is here — does not
       trip the test. */
    expect(WORKER).not.toMatch(/\bcaches\b/);
    expect(WORKER).not.toMatch(/\bnew Cache\b/);
  });

  it("does not take over open pages", () => {
    /* skipWaiting + clients.claim is the pair that makes a caching worker
       dangerous, and it buys a push-only worker nothing. Absent here so it is
       not sitting ready for whoever adds a fetch handler later. */
    expect(WORKER).not.toMatch(/skipWaiting/);
    expect(WORKER).not.toMatch(/clients\.claim/);
  });

  it("handles the two events it exists for", () => {
    expect(WORKER).toMatch(/addEventListener\(\s*["'`]push["'`]/);
    expect(WORKER).toMatch(/addEventListener\(\s*["'`]notificationclick["'`]/);
  });

  it("shows something of its own for a push it cannot read", () => {
    /* A push handler that throws, or that shows no notification, gets the
       browser's own "This site has been updated in the background" — a
       notification this product did not write, in a voice that is not
       Masterji's. The guard is that showNotification is reached with a
       fallback rather than only from a parsed payload. */
    expect(WORKER).toMatch(/showNotification/);
    expect(WORKER).toMatch(/data\.title \|\|/);
    expect(WORKER).toMatch(/data\.body \|\|/);
  });
});

/* Four lines of padding arithmetic that no browser complains about when it is
   wrong: a key decoded one byte short is accepted by `subscribe()` and
   produces a subscription this server can never sign for. The only symptom in
   production is notifications that never arrive, with nothing in any log. */
describe("the VAPID public key", () => {
  /* A real-shaped key: 65 bytes (an uncompressed P-256 point, 0x04 followed
     by two 32-byte coordinates), base64url encoded to 87 characters with no
     padding — which is exactly the length that needs one '=' added back. */
  const key =
    "BEl6" + "A".repeat(83);

  it("decodes to the 65 bytes a P-256 point is", () => {
    expect(key).toHaveLength(87);
    expect(decodeKey(key)).toHaveLength(65);
  });

  it("restores padding rather than dropping the last bytes", () => {
    // "AAAA" is four characters — already a whole group, so padEnd must add
    // nothing. The off-by-one version of this pads it to eight and decodes
    // six bytes out of three.
    expect(decodeKey("AAAA")).toEqual(new Uint8Array([0, 0, 0]));
    // Two characters short of a group: one byte, with two '=' restored.
    expect(decodeKey("_w")).toEqual(new Uint8Array([255]));
  });

  it("reads base64URL, not base64", () => {
    // '-' and '_' are the url-safe stand-ins for '+' and '/'. A decoder that
    // forgets them throws on roughly one key in two.
    expect(decodeKey("-_8")).toEqual(new Uint8Array([251, 255]));
  });
});
