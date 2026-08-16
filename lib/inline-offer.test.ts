import { describe, expect, it } from "vitest";
import {
  cardIndex,
  liveAnchor,
  liveOffer,
  nextAnchor,
  type OfferAnchor,
  type OfferFacts,
  type OfferToday,
} from "./inline-offer";

/** What these protect: that a commit card inside the chat log can never outlive
 * the offer it commits.
 *
 * That is #219's failure class — a door offered that cannot be opened — and it
 * is the one rule the inline card is dangerous without. Every case here is a
 * moment nobody can drive in a browser without waiting for it: a draft filed
 * three turns ago, a draft rewritten mid-conversation, and midnight passing
 * under an open tab.
 *
 * No DOM and no clock: the date is an argument, for the reason `eveningOpen`'s
 * hour is one — the caller keeps the property and a test can drive both sides.
 */

const TODAY = "2026-08-16";

/** Today's row with nothing interesting on it. Every test names the two or
 * three fields it has an opinion about and inherits the rest. */
function row(over: Partial<OfferToday> = {}): OfferToday {
  return {
    id: 44,
    amDeclaration: "Interview the mess aunty about the 9pm rush",
    pmProofText: "",
    proofStatus: "NONE",
    proofOffer: "",
    proofMissing: "",
    metricOffer: null,
    ...over,
  };
}

function facts(over: Partial<OfferFacts> = {}): OfferFacts {
  return { declarationOffer: "", today: row(), ...over };
}

describe("liveOffer", () => {
  it("offers the morning's draft only while nothing is declared", () => {
    const draft = "Interview the mess aunty about the 9pm rush";
    // No row at all: the commonest shape of a morning, since the row is created
    // BY declaring.
    const before = liveOffer({ declarationOffer: draft, today: null });
    expect(before?.kind).toBe("declare");
    expect(before?.text).toBe(draft);
    // The same draft against a declared task. DeclareView spends the offer on
    // the same write, so the server would not send this pair — and if it ever
    // did, the card must not sit over a row that already reads "Declared:".
    expect(liveOffer({ declarationOffer: draft, today: row() })).toBeNull();
  });

  it("offers tonight's draft while the cycle still owes a proof, and stops when it settles", () => {
    const draft = "Priya, 2nd yr, Block C. Paid ₹210 for about ₹90 of food…";
    expect(liveOffer(facts({ today: row({ proofOffer: draft }) }))?.kind).toBe("prove");
    // Filed and accepted: the evening is over and so is the control.
    expect(
      liveOffer(
        facts({
          today: row({ proofOffer: draft, pmProofText: draft, proofStatus: "ACCEPTED" }),
        }),
      ),
    ).toBeNull();
    // Filed and pushed back, or filed and unread — both leave tonight open, so
    // both keep the card. This is the pair that a naive "has a proof text" test
    // would get wrong in the direction that costs the builder the evening.
    for (const status of ["PUSHED_BACK", "UNJUDGED"] as const) {
      expect(
        liveOffer(
          facts({ today: row({ proofOffer: draft, pmProofText: draft, proofStatus: status }) }),
        ),
        status,
      ).not.toBeNull();
    }
  });

  it("offers an incomplete draft too, and carries what it still lacks", () => {
    // "Complete or not" is the product decision, not an accident: an incomplete
    // draft is filed on its merits today, and the inline card does not change
    // that. What it must not do is show one without the gap.
    const offer = liveOffer(
      facts({
        today: row({
          proofOffer: "Spoke to Priya about the 9pm rush",
          proofMissing: "what she last did about it; what you asked her for",
        }),
      }),
    );
    expect(offer?.missing).toBe("what she last did about it; what you asked her for");
  });

  it("carries the number the draft came with, and zero is a reading", () => {
    expect(liveOffer(facts({ today: row({ proofOffer: "d", metricOffer: 0 }) }))?.metric).toBe(0);
    expect(liveOffer(facts({ today: row({ proofOffer: "d" }) }))?.metric).toBeNull();
  });

  it("gives a rewritten draft a different identity from the one it replaced", () => {
    // The whole of "replaced" as far as the card is concerned. Same evening,
    // same row, one more piece written down — and the card drawn against the
    // old wording has to go dark rather than quietly re-label itself.
    const before = liveOffer(facts({ today: row({ proofOffer: "Spoke to Priya" }) }));
    const after = liveOffer(
      facts({ today: row({ proofOffer: "Spoke to Priya. She paid ₹210 for ₹90 of food." }) }),
    );
    expect(before!.key).not.toBe(after!.key);
    // And so does a second cycle on the same day whose draft happens to read
    // the same, which the date alone could never tell apart.
    const first = liveOffer(facts({ today: row({ id: 44, proofOffer: "Shipped it" }) }));
    const second = liveOffer(facts({ today: row({ id: 45, proofOffer: "Shipped it" }) }));
    expect(first!.key).not.toBe(second!.key);
    // The gap and the number are part of what the card shows, so they are part
    // of what it means for a draft to be the same draft.
    const gapped = liveOffer(
      facts({ today: row({ proofOffer: "Spoke to Priya", proofMissing: "what she last did" }) }),
    );
    expect(before!.key).not.toBe(gapped!.key);
  });
});

describe("the anchor", () => {
  const KEY = "prove:44::  :Spoke to Priya";

  it("lands the card under the words that drafted it, and leaves it there", () => {
    const laid = nextAnchor(null, KEY, 12, TODAY);
    expect(laid).toEqual({ key: KEY, afterMessageId: 12, date: TODAY });
    // Three more turns go by. The card keeps its place in the transcript — it
    // is keyed to a position, not pinned to the bottom of the log.
    expect(nextAnchor(laid, KEY, 15, TODAY)).toBe(laid);
  });

  it("forgets the position the moment the offer goes", () => {
    const laid = nextAnchor(null, KEY, 12, TODAY);
    expect(nextAnchor(laid, null, 15, TODAY)).toBeNull();
  });

  it("moves to the newest turn when the draft is rewritten", () => {
    const laid = nextAnchor(null, KEY, 12, TODAY);
    const moved = nextAnchor(laid, KEY + " who paid ₹210", 15, TODAY);
    expect(moved).toEqual({ key: KEY + " who paid ₹210", afterMessageId: 15, date: TODAY });
    // ...and the old position draws nothing, which is the half that matters.
    expect(liveAnchor(laid, KEY + " who paid ₹210", TODAY)).toBeNull();
  });
});

describe("liveAnchor", () => {
  const laid: OfferAnchor = { key: "declare:Interview the mess aunty", afterMessageId: 12, date: TODAY };

  it("draws the card while the offer it points at is still the live one", () => {
    expect(liveAnchor(laid, laid.key, TODAY)).toBe(laid);
  });

  it("goes dark once the draft is filed", () => {
    // Filing is what makes the offer null: DeclareView spends the declaration
    // draft on the same write, and an accepted proof closes the cycle. So the
    // scrollback card is not disabled — it is not there.
    expect(liveAnchor(laid, null, TODAY)).toBeNull();
  });

  it("goes dark once a replacement draft exists", () => {
    expect(liveAnchor(laid, "declare:Interview two people at the 9pm rush", TODAY)).toBeNull();
  });

  it("goes dark when the day turns under an open tab", () => {
    // The one that cannot be caught by watching the server: the payload on
    // screen was true when it arrived and is not true any more. Yesterday's
    // card must never declare today.
    expect(liveAnchor(laid, laid.key, "2026-08-17")).toBeNull();
    // And it stays dark rather than re-stamping itself on the next render.
    const held = nextAnchor(laid, laid.key, 40, "2026-08-17");
    expect(held).toBe(laid);
    expect(liveAnchor(held, laid.key, "2026-08-17")).toBeNull();
  });
});

describe("cardIndex", () => {
  it("puts the card after the message it arrived beside", () => {
    expect(cardIndex({ key: "k", afterMessageId: 12, date: TODAY }, [10, 11, 12, 13])).toBe(2);
  });

  it("falls back to the newest turn when that message has aged out of the payload", () => {
    // The state payload is capped, so a long conversation eventually trims the
    // turn the draft arrived beside. The offer is still live; losing its only
    // inline surface to a truncation would be the wrong half to drop.
    expect(cardIndex({ key: "k", afterMessageId: 3, date: TODAY }, [10, 11, 12])).toBe(2);
  });

  it("answers -1 for a log with nothing in it, and null for no anchor", () => {
    expect(cardIndex({ key: "k", afterMessageId: null, date: TODAY }, [])).toBe(-1);
    expect(cardIndex(null, [10, 11])).toBeNull();
  });
});
