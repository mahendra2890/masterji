// The wire both live turns speak.
//
// The coaching chat and the workshop stream the same format: one JSON object
// per line, newline-terminated, written by `_line` in `backend/coach/views.py`.
// Until this file existed each of them hand-rolled the same reader, and a
// reader copied twice is a reader that gets fixed once.
//
// That is not a style complaint. The failure mode of getting this wrong is a
// dropped event, and the events on these two wires are a gate verdict, a
// proposed close, a parked candidate and an IDEA sketch — a dropped one is a
// builder watching the thing they just earned fail to appear.

/** A reader that turns chunks of text into whole events, holding back what is
 * not whole yet.
 *
 * Call it with each chunk as it arrives; it returns the events that completed
 * on that chunk, in order, and keeps the rest for the next one. Chunk
 * boundaries are the entire difficulty here and they are not hypothetical: a
 * `delta` carrying a sentence is exactly the size that arrives in two pieces,
 * and the buffer is what makes the first piece wait for the second.
 *
 * A function over strings rather than over a `ReadableStreamDefaultReader`,
 * because that is the shape `npm run test:web` can drive — no DOM, no
 * `TextDecoder`, no browser, by decision rather than by omission (#117). This
 * is the pattern that decision leans on: lift the rule out, keep it generic
 * over whatever the DOM would have supplied, drive the thin remainder in a
 * browser. What is left for the browser is four lines — get a reader, decode,
 * loop, hand each event on.
 *
 * Nothing is flushed when the stream ends, and that is deliberate rather than
 * forgotten: every event the server writes ends in a newline, so anything left
 * in the buffer is half of an event from a stream that was cut. Parsing it
 * would replace a turn that merely stopped early with a thrown exception, and
 * a truncated answer the builder can still read is worth more than that.
 */
export function ndjsonFeed<T = unknown>(): (chunk: string) => T[] {
  // The half-line carried between chunks.
  let buffer = "";
  return (chunk: string): T[] => {
    buffer += chunk;
    const lines = buffer.split("\n");
    // The last piece is either "" — the chunk happened to end on a newline —
    // or the beginning of an event whose rest has not arrived. Those are the
    // same case and both are answered by putting it back.
    buffer = lines.pop() ?? "";
    const events: T[] = [];
    for (const raw of lines) {
      // The server writes no blank lines, so this guards against the format
      // rather than against today's writer: a trailing newline on the last
      // event would otherwise arrive here as `JSON.parse("")`.
      if (!raw.trim()) continue;
      events.push(JSON.parse(raw) as T);
    }
    return events;
  };
}
