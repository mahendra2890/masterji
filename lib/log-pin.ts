// Where a conversation log should sit after a turn lands.
//
// Two logs in this app scroll: the chat (`.messages`) and the room's
// (`.workshopLog`). Both used to do the same one line — `scrollTop =
// scrollHeight` — and that is right for a conversation and wrong for a single
// turn that is taller than the window it arrives in. Measured on a real
// first-run account at 390×844: the welcome message is 107 words and 477px
// tall, the log is 452px, and pinning to the bottom put the first thing
// Masterji ever says 207px past its own opening. A new builder's first contact
// with the coach began mid-clause, and the only way to the start was to scroll
// up in a log they had no reason to think had anything above it.
//
// The room needs it more than the chat does. `.workshopLog` is capped at 320px
// against the chat's `calc(100dvh - 110px)`, so a coaching turn overruns it far
// sooner — the workshop's tiebreak measures 250–400px on a phone against that
// 320px window. Same failure, tighter margin, which is why this landed once for
// both rather than twice.

/** A log and its newest turn, measured. All in CSS pixels.
 *
 * `newestTop` is the newest turn's top edge relative to the log's own top edge,
 * as the log is scrolled right now — so it goes negative once that turn has
 * scrolled off. Relative rather than absolute because the caller reads it off
 * two `getBoundingClientRect()`s, which is the one measurement that survives a
 * future `position: relative` on the log; `offsetTop` would quietly start
 * meaning something else the day anyone adds one.
 */
export type LogMetrics = {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
  newestTop: number;
  newestHeight: number;
};

/** The scrollTop the log should be left at.
 *
 * Anything at or past the real maximum pins to the bottom, so `scrollHeight` is
 * the honest way to say "the bottom" without asking the caller to do the
 * subtraction — the browser clamps it.
 *
 * The top-pin needs no clamp of its own, and the arithmetic is why: a turn
 * taller than the log starts at most `scrollHeight - newestHeight` into the
 * content, and `newestHeight > clientHeight` makes that strictly less than
 * `scrollHeight - clientHeight`, which is the maximum. A turn that cannot fit
 * can always be scrolled to its own top.
 */
export function logScrollTop(m: LogMetrics, streaming: boolean): number {
  // Words arriving. The builder is watching the end of the line being written,
  // and moving the log out from under that is the one thing worse than opening
  // mid-clause. The settled case below is the only one this file changes.
  if (streaming) return m.scrollHeight;
  // A turn that fits is a conversation, and a conversation pins to the bottom —
  // the newest thing said, last, where it has been since the first version of
  // this. Nothing about the ordinary case moves.
  if (m.newestHeight <= m.clientHeight) return m.scrollHeight;
  return m.scrollTop + m.newestTop;
}

/** Measure a log and pin it. The thin half: everything decidable is above.
 *
 * `[data-turn]` rather than the last element child, because the last child of
 * the chat log is not always a turn — the openers block ("Not sure where to
 * start? Ask him:") renders inside `.messages`, under the welcome, on exactly
 * the first-run screen this exists for. Pinning to the last child there would
 * measure the openers, find them short, and bottom-pin the log the same as
 * before, fixing nothing on the one screen it was filed about.
 */
export function pinLog(box: HTMLElement | null, streaming: boolean): void {
  if (!box) return;
  const turns = box.querySelectorAll<HTMLElement>("[data-turn]");
  const newest = turns[turns.length - 1];
  const rect = newest?.getBoundingClientRect();
  box.scrollTop = logScrollTop(
    {
      scrollTop: box.scrollTop,
      scrollHeight: box.scrollHeight,
      clientHeight: box.clientHeight,
      newestTop: rect ? rect.top - box.getBoundingClientRect().top : 0,
      newestHeight: rect ? rect.height : 0,
    },
    streaming,
  );
}
