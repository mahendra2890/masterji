import { afterEach, describe, expect, it, vi } from "vitest";
import { DRAFT_MAX_AGE_MS, DRAFT_PREFIX, readDraft, writeDraft } from "./drafts";

/** What these protect: the rules that decide whether an evening's typing comes
 * back after a phone discards the tab. Every one of them is arithmetic over a
 * key, a timestamp and a string — invisible on screen, and exactly the kind of
 * thing that regresses silently on an unrelated refactor. Driving the browser
 * cannot reach them: the expiry needs a clock eighteen hours ahead, and the
 * storage failures need a localStorage that throws.
 *
 * No DOM: these two functions need `window.localStorage` and `Date.now()`, so a
 * stub supplies both. The parts of #82 that DO need rendering — restore once
 * per key, only into an empty box — are not covered here and will not be:
 * #117 decided against a rendering harness, and those rules are driven in a
 * browser instead. */

/** localStorage as these functions use it, over a Map. `fails` is the Safari
 * private-mode case: the property access itself throws. */
function fakeStorage(fails: "none" | "read" | "write" = "none") {
  const store = new Map<string, string>();
  return {
    store,
    getItem: (k: string) => {
      if (fails === "read") throw new Error("SecurityError");
      return store.get(k) ?? null;
    },
    setItem: (k: string, v: string) => {
      if (fails === "write") throw new Error("QuotaExceededError");
      store.set(k, v);
    },
    removeItem: (k: string) => void store.delete(k),
  };
}

function install(fails: "none" | "read" | "write" = "none") {
  const localStorage = fakeStorage(fails);
  vi.stubGlobal("window", { localStorage });
  return localStorage;
}

afterEach(() => vi.unstubAllGlobals());

describe("readDraft", () => {
  it("gives back what was typed, until it is too old to be tonight's", () => {
    const s = install();
    writeDraft("g1.pm.44", "Priya ordered again on Thursday");
    expect(readDraft("g1.pm.44")).toBe("Priya ordered again on Thursday");

    // Written just inside the window and just outside it. The pair is the
    // point: without the fresh case above and this one, every assertion here
    // would pass on a function that always returned "".
    const key = DRAFT_PREFIX + "g1.pm.44";
    s.store.set(key, JSON.stringify({ v: "still tonight", at: Date.now() - DRAFT_MAX_AGE_MS + 60_000 }));
    expect(readDraft("g1.pm.44")).toBe("still tonight");
    s.store.set(key, JSON.stringify({ v: "last week", at: Date.now() - DRAFT_MAX_AGE_MS - 1 }));
    expect(readDraft("g1.pm.44")).toBe("");
  });

  it("deletes the stale one rather than stepping over it", () => {
    // A paragraph from last week reappearing under tonight's task is worse
    // than losing it, and a read that only declined to return it would leave
    // it there to be read again by every later render.
    const s = install();
    s.store.set(
      DRAFT_PREFIX + "g1.pm.44",
      JSON.stringify({ v: "last week", at: Date.now() - DRAFT_MAX_AGE_MS - 1 }),
    );
    readDraft("g1.pm.44");
    expect(s.store.has(DRAFT_PREFIX + "g1.pm.44")).toBe(false);
  });

  it("reads anything hand-edited as no draft at all", () => {
    // The value is a string in a store the builder can open and type into.
    // Nothing here may reach the evening box: a number where the words should
    // be would render as one, and a missing timestamp would make the age
    // comparison NaN — which is never greater than the limit, so a draft with
    // no `at` would live forever.
    const s = install();
    for (const raw of ["{", "null", '"just a string"', '{"v":123,"at":0}', '{"v":"words"}']) {
      s.store.set(DRAFT_PREFIX + "k", raw);
      expect(readDraft("k"), raw).toBe("");
    }
  });

  it("costs the draft and never the evening when storage refuses", () => {
    // Safari in private browsing throws on the access itself. The worst this
    // feature is allowed to do is what the product did before it existed,
    // which is forget — never to take down the box it was meant to protect.
    install("read");
    expect(() => readDraft("k")).not.toThrow();
    expect(readDraft("k")).toBe("");

    const w = install("write");
    expect(() => writeDraft("k", "a paragraph typed on a phone")).not.toThrow();
    expect(w.store.size).toBe(0);
  });
});

describe("writeDraft", () => {
  it("clears the key when the box is emptied", () => {
    // The submit paths set the box to "", and this is what makes that the end
    // of the draft. Storing an empty string instead would put a filed proof's
    // own text back under tomorrow's task.
    const s = install();
    writeDraft("g1.pm.44", "filed tonight");
    expect(s.store.size).toBe(1);
    writeDraft("g1.pm.44", "");
    expect(s.store.has(DRAFT_PREFIX + "g1.pm.44")).toBe(false);
  });
});
