// The words a refused request is reported in.
//
// Split out of coach-api.ts because three senders need this and only one of
// them had it. A refusal from this API is a sentence, not a status: the gate's
// message IS the feature, and the ceilings on the paid endpoints are worded
// server-side by VoicedThrottleMixin for no other reason than that a builder
// who hit one has done nothing wrong and is being asked to come back.
//
// `send` read that sentence out. The two streaming senders each rebuilt their
// error handling around their reader instead of sharing it, and the chat's
// copy dropped the body on the floor — so the refusal a builder is most likely
// to meet (thirty turns an hour) arrived as "Masterji said no (429)." with the
// coach's own words sitting unread in the response. One reader, three callers,
// nothing left to drift.

/** The sentence a DRF error body is refusing in, if it has one.
 *
 * DRF sends `{"detail": ...}` or field errors; the gate sends its refusal in
 * `detail` alongside non-string fields, so `detail` is checked by name before
 * anything is scanned for.
 */
export function refusalIn(body: unknown): string | undefined {
  if (typeof body !== "object" || body === null) return undefined;
  const fields = body as Record<string, unknown>;
  if (typeof fields.detail === "string") return fields.detail;
  const first = Object.values(fields)
    .flat()
    .find((v) => typeof v === "string");
  return typeof first === "string" ? first : undefined;
}

/** What to tell the builder about a response that refused them.
 *
 * The status-code line is the last resort and reads like one — it is for a
 * refusal with nothing to say: a proxy's own error page, an empty body, a 502
 * that never reached Django. Anything the server actually worded wins over it.
 */
export async function refusalFrom(res: Response): Promise<string> {
  const body = await res.json().catch(() => undefined);
  return refusalIn(body) ?? `Masterji said no (${res.status}).`;
}
