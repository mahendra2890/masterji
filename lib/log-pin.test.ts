import { describe, expect, it } from "vitest";
import { logScrollTop } from "./log-pin";

/** What these protect: the first thing Masterji ever says is 107 words, and on
 * a phone it is taller than the log it arrives in. Bottom-pinning a turn like
 * that opens it 207px past its own opening, which is where a new builder's
 * first contact with the coach used to begin. The three cases below are the
 * whole rule — the one that moves, and the two that must not, because
 * bottom-pinning is still right for a conversation and still right while words
 * are arriving. */
describe("logScrollTop", () => {
  // The welcome, measured on a real first-run account at 390×844: a 477px
  // message in a 452px log, which the old rule left at scrollTop 224 with the
  // message's top 207px above the log's.
  const welcome = {
    scrollTop: 224,
    scrollHeight: 676,
    clientHeight: 452,
    newestTop: -207,
    newestHeight: 477,
  };

  it("shows the start of a turn too tall to fit", () => {
    expect(logScrollTop(welcome, false)).toBe(17);
  });

  it("leaves a conversation pinned to the bottom", () => {
    // Two-line reply in the same log. This is the ordinary case and the reason
    // the original one-liner was written; nothing here may change.
    expect(
      logScrollTop(
        { ...welcome, scrollTop: 40, newestTop: 380, newestHeight: 64 },
        false,
      ),
    ).toBe(676);
  });

  it("keeps the bottom while the reply is still arriving", () => {
    // Same overrunning turn as the first case, mid-stream. The builder is
    // watching the words land; scrolling back to the opening under them would
    // take the sentence they are reading off the screen.
    expect(logScrollTop(welcome, true)).toBe(676);
  });
});
