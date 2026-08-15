// Reading the conversation log back.
//
// Pure and separate for the reason #117 settled: this is decidable arithmetic
// over data the payload already holds, so it is pinned here, and the button
// that carries the answer is driven in a browser.

import type { ChatMessage } from "./coach-api";

/** The words a SYSTEM notice is about: the last thing the builder said before
 * it, which is the turn that never landed — and the words the notice's retry
 * button will re-send.
 *
 * Searched backwards rather than read off `i - 1`. What this feeds is a button
 * that SENDS, so the one thing it must never do is put somebody else's
 * sentence in the builder's mouth — and "the row above" is an assumption about
 * how the server writes rows, while "the last thing they said" is the actual
 * question. A notice can be written after a COACH row, after a second notice,
 * or first in the log.
 *
 * Empty means no retry button, which is right for a notice with nothing behind
 * it rather than a button that would send "".
 */
export function saidBefore(messages: readonly Pick<ChatMessage, "role" | "content">[], i: number): string {
  for (let n = i - 1; n >= 0; n--) {
    if (messages[n].role === "USER") return messages[n].content;
  }
  return "";
}
