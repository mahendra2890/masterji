import { describe, expect, it } from "vitest";
import { ndjsonFeed } from "./ndjson";

/** What these protect: both of this app's live turns arrive down this reader,
 * and everything the server has to say that is not prose arrives as one of
 * these events — the gate's verdict, the close box, a parked candidate, the
 * IDEA sketch. The network decides where the chunks break and it does not
 * break them on event boundaries, so "an event split in two" is the ordinary
 * case rather than the edge one. A reader that loses one of those loses a
 * builder's phase advance, silently, on a turn that otherwise looked fine. */
describe("ndjsonFeed", () => {
  // Real lines off `coach.turn`, in the order a turn that advances a phase
  // sends them. `_line` in views.py writes exactly this: JSON, then "\n".
  const DELTA = '{"t":"delta","text":"Good. "}';
  const GATE = '{"t":"gate","advanced":true,"phase":"BUILD","detail":"Moved."}';
  const DONE = '{"t":"done"}';

  it("hands back every event that completed in one chunk, in order", () => {
    const feed = ndjsonFeed();
    expect(feed(`${DELTA}\n${GATE}\n${DONE}\n`)).toEqual([
      { t: "delta", text: "Good. " },
      { t: "gate", advanced: true, phase: "BUILD", detail: "Moved." },
      { t: "done" },
    ]);
  });

  it("waits for the rest of an event instead of dropping it", () => {
    // The case this whole buffer exists for. A `delta` carrying a sentence is
    // routinely bigger than one chunk, and the half that arrives first is not
    // parseable JSON.
    const feed = ndjsonFeed();
    expect(feed('{"t":"delta","te')).toEqual([]);
    expect(feed('xt":"Good. "}\n')).toEqual([{ t: "delta", text: "Good. " }]);
  });

  it("survives a stream that arrives one character at a time", () => {
    // The worst case the network can produce, and the one that would catch a
    // reader that only handles a single split.
    const feed = ndjsonFeed();
    const wire = `${DELTA}\n${GATE}\n`;
    const seen = wire.split("").flatMap((c) => feed(c));
    expect(seen).toEqual([
      { t: "delta", text: "Good. " },
      { t: "gate", advanced: true, phase: "BUILD", detail: "Moved." },
    ]);
  });

  it("keeps order when one chunk ends mid-event and the next carries two", () => {
    // The interleaving that a naive "parse whatever is in the buffer" reader
    // gets wrong: the held-back half must come out BEFORE the events that
    // arrived after it, not appended to the end.
    const feed = ndjsonFeed();
    expect(feed(`${DELTA}\n{"t":"clo`)).toEqual([{ t: "delta", text: "Good. " }]);
    expect(feed(`se"}\n${DONE}\n`)).toEqual([{ t: "close" }, { t: "done" }]);
  });

  it("never emits a final event that has no newline behind it", () => {
    // The deliberate no-flush. A stream cut mid-event leaves half an object in
    // the buffer, and parsing it would turn a turn that merely stopped early
    // into a thrown exception — the builder loses a readable partial answer
    // and gets an error banner instead.
    const feed = ndjsonFeed();
    expect(feed(`${DELTA}\n{"t":"do`)).toEqual([{ t: "delta", text: "Good. " }]);
    expect(feed("")).toEqual([]);
  });

  it("skips blank lines rather than parsing them", () => {
    // `JSON.parse("")` throws, so this guard is what makes the reader safe
    // against the format rather than only against today's writer.
    const feed = ndjsonFeed();
    expect(feed(`\n${DELTA}\n\n${DONE}\n`)).toEqual([
      { t: "delta", text: "Good. " },
      { t: "done" },
    ]);
  });

  it("gives each stream its own buffer", () => {
    // Two turns can be open at once — the coaching chat and the workshop are
    // no longer mutually exclusive. A buffer shared between them would splice
    // half of one turn's event onto half of the other's.
    const chat = ndjsonFeed();
    const workshop = ndjsonFeed();
    expect(chat('{"t":"del')).toEqual([]);
    expect(workshop(`${DONE}\n`)).toEqual([{ t: "done" }]);
    expect(chat('ta","text":"Good. "}\n')).toEqual([
      { t: "delta", text: "Good. " },
    ]);
  });
});
