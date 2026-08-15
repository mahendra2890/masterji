import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  dayOpen,
  draftWaiting,
  EVENING_FROM,
  eveningOpen,
  isUnsettled,
  missingPieces,
  notesRunning,
  type TodayFacts,
} from "./day";
import type { CheckIn } from "./coach-api";

/** A check-in in the state a builder leaves it in most of the day: declared
 * this morning, nothing filed yet. Every test below names only the fields it
 * is about. */
const today = (over: Partial<TodayFacts> = {}): TodayFacts => ({
  amDeclaration: "Message ten hostel wardens",
  pmProofText: "",
  proofStatus: "NONE",
  proofOffer: "",
  proofMissing: "",
  attempts: [],
  ...over,
});

/** What these protect: the Today card's rules used to live as expressions
 * inside JSX, in the one frontend file no test can reach. They decide what a
 * builder is shown every evening — whether tonight's box is on screen at all,
 * and which of three sentences the other pane offers. */
describe("isUnsettled", () => {
  it("is the two statuses that leave tonight open", () => {
    // Opposites, and that is the point of one predicate over them: Masterji
    // read the proof and wants more, or he never read it at all.
    expect(isUnsettled("PUSHED_BACK")).toBe(true);
    expect(isUnsettled("UNJUDGED")).toBe(true);
  });

  it("is not a day with nothing filed, or one that is done", () => {
    expect(isUnsettled("NONE")).toBe(false);
    expect(isUnsettled("ACCEPTED")).toBe(false);
  });

  /** The one that is worth more than the four assertions above.
   *
   * `isUnsettled`'s own comment says it mirrors `views.UNSETTLED`, which
   * decides the same thing server-side — and until this test there was nothing
   * holding either end. Restating "PUSHED_BACK and UNJUDGED" in a second file
   * would not have been that: a client test that agrees with the client proves
   * only that the client agrees with itself, and the failure worth catching is
   * the server changing while the card does not.
   *
   * So the server's own tuple is read out of `views.py` and every status the
   * model can hold is classified by both sides and compared.
   *
   * What this CAN catch: a status added to or removed from `views.UNSETTLED`;
   * a status added to or removed from `CheckIn.ProofStatus`; either one
   * renamed. All of them fail here, in the frontend suite, pointing at the
   * Python file that moved.
   *
   * What it CANNOT: anything about how the server USES the tuple. `views.py`
   * has a second site (the one commented "PUSHED_BACK only, and deliberately
   * not UNSETTLED") which is a different decision by design, and a bug that
   * swapped one for the other is invisible from here. It also cannot see a
   * disagreement in meaning while the members match, and it is a text match
   * over source, not an executed import — a tuple built by a loop, an alias,
   * or a value assembled at runtime would defeat the parse. The parse failing
   * is a failing test rather than a silent pass, which is the only property
   * that makes the rest of it worth anything.
   */
  it("holds exactly the statuses views.UNSETTLED holds", () => {
    const views = readFileSync(new URL("../backend/coach/views.py", import.meta.url), "utf8");
    const tuple = views.match(/^UNSETTLED = \(([^)]*)\)/m);
    expect(tuple, "views.py no longer declares UNSETTLED as a literal tuple").not.toBeNull();
    const serverUnsettled = [...tuple![1].matchAll(/CheckIn\.ProofStatus\.(\w+)/g)].map(
      (m) => m[1],
    );
    expect(serverUnsettled.length).toBeGreaterThan(0);

    // Every status the column can hold, read off the model rather than listed
    // here — so a fifth one arrives in this test instead of going unnoticed.
    const models = readFileSync(new URL("../backend/coach/models.py", import.meta.url), "utf8");
    const block = models.match(/class ProofStatus\(models\.TextChoices\):\n([\s\S]*?)\n\n/);
    expect(block, "models.py no longer declares ProofStatus as a TextChoices block").not.toBeNull();
    const statuses = [...block![1].matchAll(/^ {8}(\w+) = "(\w+)"/gm)].map((m) => m[2]);
    // The names and the wire values are the same string for all of these, which
    // is what lets the tuple above be compared against the payload's strings.
    expect(statuses).toEqual(["NONE", "ACCEPTED", "PUSHED_BACK", "UNJUDGED"]);

    const clientUnsettled = statuses.filter((s) => isUnsettled(s as CheckIn["proofStatus"]));
    expect(clientUnsettled.sort()).toEqual([...serverUnsettled].sort());
  });
});

describe("missingPieces", () => {
  it("splits the server's phrases and trims them", () => {
    expect(missingPieces("who you spoke to; what they said")).toEqual([
      "who you spoke to",
      "what they said",
    ]);
  });

  it("is empty for nothing owed, and for a string of separators", () => {
    // Empty means the draft clears the bar, which is what decides whether
    // filing it unedited skips the evening's judgement. A stray semicolon
    // must not read as a piece — an owed count of 1 over no phrase at all
    // would put "1 piece" on the composer with nothing to name.
    expect(missingPieces("")).toEqual([]);
    expect(missingPieces(" ; ; ")).toEqual([]);
  });
});

describe("dayOpen", () => {
  it("is open before anything is declared", () => {
    // Including the case with no row at all: a builder who has not declared
    // has the whole day ahead of them, not a finished one.
    expect(dayOpen(null)).toBe(true);
    expect(dayOpen(undefined)).toBe(true);
    expect(dayOpen(today({ amDeclaration: "" }))).toBe(true);
  });

  it("is open with the morning done and nothing filed", () => {
    expect(dayOpen(today())).toBe(true);
  });

  it("stays open on a proof that has not settled", () => {
    // The whole reason isUnsettled exists: filed is not finished.
    expect(dayOpen(today({ pmProofText: "Talked to 4", proofStatus: "PUSHED_BACK" }))).toBe(true);
    expect(dayOpen(today({ pmProofText: "Talked to 4", proofStatus: "UNJUDGED" }))).toBe(true);
  });

  it("closes only on a declaration, a proof, and a verdict", () => {
    expect(dayOpen(today({ pmProofText: "Talked to 4", proofStatus: "ACCEPTED" }))).toBe(false);
  });
});

describe("draftWaiting", () => {
  it("is a finished draft nobody has filed", () => {
    // The state the dot on the other pane exists for.
    expect(draftWaiting(today({ proofOffer: "Spoke to 3 wardens; 2 said yes" }))).toBe(true);
  });

  it("is not lit while pieces are still owed", () => {
    // Running notes are the evening's working-out. Lighting the dot on them
    // would relight it on nearly every turn and teach the builder it means
    // nothing — which is the whole distinction from notesRunning below.
    expect(
      draftWaiting(today({ proofOffer: "Spoke to 3", proofMissing: "what they said" })),
    ).toBe(false);
  });

  it("is not lit with no draft at all", () => {
    expect(draftWaiting(today())).toBe(false);
    expect(draftWaiting(null)).toBe(false);
  });

  it("is not lit once the day is closed", () => {
    // A draft left over from a cycle that has already been proved and accepted
    // is not something on the other pane to do.
    expect(
      draftWaiting(
        today({ proofOffer: "Spoke to 3", pmProofText: "Spoke to 3", proofStatus: "ACCEPTED" }),
      ),
    ).toBe(false);
  });
});

describe("notesRunning", () => {
  it("is a draft with pieces still owed", () => {
    expect(
      notesRunning(today({ proofOffer: "Spoke to 3", proofMissing: "what they said" })),
    ).toBe(true);
  });

  it("is not a finished draft — that is draftWaiting", () => {
    // The two are exclusive, and the composer note picks between them. Both
    // true at once would be two sentences claiming the same line.
    const finished = today({ proofOffer: "Spoke to 3 wardens; 2 said yes" });
    expect(notesRunning(finished)).toBe(false);
    expect(draftWaiting(finished)).toBe(true);
  });

  it("is not lit by separators that name no piece", () => {
    // Where the two rules read `proofMissing` differently: a lone semicolon is
    // missing text, so the draft is not finished — but it owes no piece anyone
    // can be shown, so neither sentence is offered.
    const punctuation = today({ proofOffer: "Spoke to 3", proofMissing: ";" });
    expect(notesRunning(punctuation)).toBe(false);
    expect(draftWaiting(punctuation)).toBe(false);
  });
});

describe("eveningOpen", () => {
  const morning = 9;
  const evening = EVENING_FROM;

  it("is folded in the morning for a builder who has only declared", () => {
    // The one state the fold exists for. Everything else below opens it.
    expect(eveningOpen(today(), morning, false)).toBe(false);
  });

  it("opens on the clock, and on the hour named rather than after it", () => {
    // Both sides of EVENING_FROM, which is the reason the hour is an argument.
    expect(eveningOpen(today(), evening - 1, false)).toBe(false);
    expect(eveningOpen(today(), evening, false)).toBe(true);
    expect(eveningOpen(today(), 23, false)).toBe(true);
  });

  it("opens at any hour for a builder who has not declared yet", () => {
    // Nothing is folded away from someone with no morning on the record.
    expect(eveningOpen(today({ amDeclaration: "" }), morning, false)).toBe(true);
    expect(eveningOpen(null, morning, false)).toBe(true);
  });

  it("opens on owed work, on an earlier try, and on a draft", () => {
    // Each of these is an evening that has already started, hours or not.
    expect(eveningOpen(today({ proofStatus: "PUSHED_BACK" }), morning, false)).toBe(true);
    expect(eveningOpen(today({ proofStatus: "UNJUDGED" }), morning, false)).toBe(true);
    expect(eveningOpen(today({ attempts: [{}] }), morning, false)).toBe(true);
    // Running notes open it too, finished or not: hiding them would undo what
    // running notes are for.
    expect(eveningOpen(today({ proofOffer: "Spoke to 3", proofMissing: "who" }), morning, false))
      .toBe(true);
  });

  it("opens on the builder's own press, and nothing closes it again", () => {
    // "Filing now" only ever forces it open — finished early, or filing at
    // four because they're out at seven.
    expect(eveningOpen(today(), morning, true)).toBe(true);
    expect(eveningOpen(null, 3, true)).toBe(true);
    expect(
      eveningOpen(
        today({ pmProofText: "Spoke to 3", proofStatus: "ACCEPTED" }),
        morning,
        true,
      ),
    ).toBe(true);
  });

  it("stays open in the evening on a day that is already done", () => {
    // A proved and accepted day still shows its evening half — the proof is
    // there to read, and "Declare another task" lives under it.
    expect(
      eveningOpen(today({ pmProofText: "Spoke to 3", proofStatus: "ACCEPTED" }), evening, false),
    ).toBe(true);
  });
});
