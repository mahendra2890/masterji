// Turning a file the API rendered into a file on the builder's device.
//
// Split from coach-api.ts and from the components for one reason: the naming
// half is pure and worth a test, and the saving half is four lines of DOM that
// no harness here will exercise — #117 decided against a rendering harness, so
// that half is driven in a browser and said so in its pull request. Keeping
// them apart means the part that can be pinned is pinned.

const FILENAME = /filename\*?=(?:UTF-8''|")?([^";]+)"?/i;

/** The name the server gave the file, read out of its `Content-Disposition`.
 *
 * The server names it, not the client. A client that built the name itself
 * would be a second copy of the naming rule, and the two would drift the day
 * one of them changed — so this reads the header, and the API exposes it
 * cross-origin (`CORS_EXPOSE_HEADERS`) for exactly this.
 *
 * `fallback` covers the header being absent, unreadable, or blocked by a proxy
 * that strips it: a download with no name is worse than a download with a dull
 * one.
 */
export function filenameFrom(header: string | null, fallback: string): string {
  const match = header?.match(FILENAME);
  // Trailing path segment only. Goal titles are free text and the server slugs
  // them, but a filename is handed straight to the browser's writer and a
  // separator in one is the single thing it must never contain.
  const name = match?.[1]?.split(/[\\/]/).pop()?.trim();
  return name || fallback;
}

/** Save text as a file. A blob rather than a link to the endpoint: the app
 * fetches through the API client so an expired session gets refreshed and
 * replayed, which a plain navigation would turn into a downloaded error page. */
export function saveTextFile(filename: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
