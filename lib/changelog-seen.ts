// The "What's new" dot's rule, lifted out of the component so it can be
// asserted without a DOM — the frontend suite pins pure decidable logic and
// drives the rendering in a browser (README, "Run it locally").

/**
 * Does the dot light?
 *
 * `seen` is the newest entry this browser has been stamped with, in the three
 * shapes the component actually holds:
 *
 * - `null` — the mount read has not answered yet. The server rendered no dot,
 *   so the first client render must not either.
 * - `""` — nothing is stored. Either this browser has never been stamped, or
 *   storage refused to answer at all (private mode, embedded webview).
 * - a `shipped_on` date — what it was holding the last time it looked.
 *
 * `latest` is the newest `shipped_on` this browser knows about, and `""` until
 * the mount fetch lands.
 *
 * The empty cases are the load-bearing half. `""` used to compare as *behind*
 * every real date, which lit the dot on the first screen after signup — an
 * unread marker for a history the reader has no relationship with. Nothing
 * stored is not the same as being behind: a browser with no stamp has never
 * looked, and there is no "since you last looked" to be on the wrong side of.
 * The stamp is written on the first mount instead, so from then on the dot
 * means exactly one thing.
 *
 * ISO dates compare correctly as strings, which is why this is `<` and not a
 * `Date` parse.
 */
export const hasUnseen = (seen: string | null, latest: string): boolean =>
  seen !== null && seen !== "" && latest !== "" && seen < latest;
