/** The VAPID public key, base64url text → the bytes `pushManager.subscribe()`
 * wants.
 *
 * Its own module, and that is about testability rather than tidiness. The rest
 * of lib/push.ts is browser-API choreography — service worker registration,
 * a permission prompt, `pushManager` — none of which exists in the runner this
 * repo's tests use, and it imports the API client, which imports the `@/`
 * alias no vitest config here resolves. This function is the one part of the
 * flow that is pure arithmetic, and it is also the only part that can be wrong
 * in a way nothing reports.
 *
 * That failure, stated plainly: a key decoded one byte short is accepted by
 * `subscribe()` and produces a subscription this server can never sign for.
 * The browser does not complain, the server stores the row, the hourly tick
 * sends, the push service accepts — and the notification never arrives, with
 * nothing in any log to say why.
 */
/* `Uint8Array<ArrayBuffer>` rather than a bare `Uint8Array`, and it is not
 * decoration: `applicationServerKey` is typed `BufferSource`, which will not
 * accept a view that might be over a `SharedArrayBuffer`. That is what
 * `Uint8Array.from()` hands back — its element type is `ArrayBufferLike` —
 * so the obvious one-liner does not type-check. Allocating the buffer here
 * pins it. */
export function decodeKey(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = base64url.padEnd(
    base64url.length + ((4 - (base64url.length % 4)) % 4),
    "=",
  );
  const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}
