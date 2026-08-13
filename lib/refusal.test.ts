import { describe, expect, it } from "vitest";
import { refusalFrom, refusalIn } from "./refusal";

/** What these protect: the ceilings on the paid endpoints are written in the
 * coach's own register server-side — VoicedThrottleMixin exists for nothing
 * else — and a client that prints the status code instead throws that away at
 * the one moment a builder is being asked to come back rather than told they
 * broke something. The chat's sender did exactly that for the whole life of
 * the cap: "Masterji said no (429)." over the top of "Too many at once. Come
 * back to it in a bit." Pinned here so the three senders can share one reading
 * instead of each keeping a copy that drifts. */
describe("refusalFrom", () => {
  it("reads the ceiling's own sentence out of a 429", async () => {
    const res = new Response(
      JSON.stringify({ detail: "Too many at once. Come back to it in a bit." }),
      { status: 429 }
    );
    expect(await refusalFrom(res)).toBe(
      "Too many at once. Come back to it in a bit."
    );
  });

  it("falls back to the status only when the refusal said nothing", async () => {
    // A proxy's HTML error page and a body that never arrived: there is no
    // sentence to read, and the status is the only thing left to say.
    expect(
      await refusalFrom(new Response("<html>502 Bad Gateway</html>", { status: 502 }))
    ).toBe("Masterji said no (502).");
    expect(await refusalFrom(new Response("", { status: 500 }))).toBe(
      "Masterji said no (500)."
    );
  });
});

describe("refusalIn", () => {
  it("prefers detail, the field every refusal here is worded in", () => {
    // The gate's shape: its sentence in `detail`, its numbers beside it.
    expect(refusalIn({ detail: "One goal at a time.", have: 0, need: 1 })).toBe(
      "One goal at a time."
    );
  });

  it("reads a field error when there is no detail", () => {
    expect(refusalIn({ content: ["This field may not be blank."] })).toBe(
      "This field may not be blank."
    );
  });

  it("has nothing to say about a body carrying no words", () => {
    expect(refusalIn({})).toBeUndefined();
    expect(refusalIn({ count: 3 })).toBeUndefined();
    expect(refusalIn(null)).toBeUndefined();
    expect(refusalIn(undefined)).toBeUndefined();
  });
});
