/** The record is fetched a page at a time, and this is the walk that puts it
 * back together.
 *
 * Worth a test of its own because every way it can go wrong is silent: a walk
 * that stops early, or one that repeats a page, hands the panel a record that
 * is short or doubled and looks exactly like a correct one. That is the
 * failure #88 and #141 were both filed for, and the client is now a place it
 * can happen.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getGoalHistory } from "./coach-api";

type Page = {
  checkins: { id: number; date: string }[];
  next_before: { date: string; id: number } | null;
};

/** A page of the server's envelope, filled in around the two fields the walk
 * actually steers on. */
const page = (ids: number[], next: number | null): Page => ({
  checkins: ids.map((id) => ({
    id,
    date: "2026-08-14",
    am_declaration: `day ${id}`,
    pm_proof_text: "",
    proof_url: "",
    proof_status: "NONE",
    coach_reaction: "",
    attempts: [],
  })) as Page["checkins"],
  next_before: next === null ? null : { date: "2026-08-14", id: next },
});

const envelope = (p: Page, total: number) => ({
  goal: {
    id: 1,
    title: "Tiffin app",
    phase: "IDEA",
    status: "ACTIVE",
    created_at: "2026-08-01T00:00:00Z",
  },
  retirement: null,
  transitions: [],
  streak: 3,
  checkins_total: total,
  ...p,
});

/** Answers each call with the next queued page. A queued `null` is a request
 * that fails, which is the branch the walk treats differently from the rest. */
function serve(pages: (Page | null)[], total: number) {
  const seen: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      seen.push(url);
      const next = pages.shift();
      if (next === undefined || next === null)
        return { ok: false, status: 500, json: async () => ({}) } as Response;
      return {
        ok: true,
        status: 200,
        json: async () => envelope(next, total),
      } as Response;
    })
  );
  return seen;
}

describe("getGoalHistory", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("follows the cursor to the end and returns every day once", async () => {
    serve([page([3, 2], 2), page([1], 1), page([0], null)], 4);
    const history = await getGoalHistory(1);
    expect(history.checkins.map((c) => c.id)).toEqual([3, 2, 1, 0]);
    expect(history.complete).toBe(true);
    expect(history.checkinsTotal).toBe(4);
  });

  it("sends the cursor it was handed, and sends none on the first call", async () => {
    const seen = serve([page([3], 3), page([2], null)], 2);
    await getGoalHistory(1);
    expect(seen[0]).not.toContain("before=");
    expect(seen[1]).toContain("before=2026-08-14&before_id=3");
  });

  it("stops at one page when the server says there is nothing further", async () => {
    const seen = serve([page([3, 2, 1], null)], 3);
    const history = await getGoalHistory(1);
    expect(seen).toHaveLength(1);
    expect(history.complete).toBe(true);
  });

  it("keeps the days it got when a later page fails, and says it is short", async () => {
    // The honest half. A builder looking for their own first week is better
    // served by the days that arrived plus a line saying so than by an error
    // where their record used to be.
    serve([page([3, 2], 2), null], 4);
    const history = await getGoalHistory(1);
    expect(history.checkins.map((c) => c.id)).toEqual([3, 2]);
    expect(history.complete).toBe(false);
    expect(history.checkinsTotal).toBe(4);
  });

  it("throws when the first page fails, because there is nothing to show", async () => {
    serve([null], 0);
    await expect(getGoalHistory(1)).rejects.toThrow();
  });

  it("gives up rather than spinning on a cursor that never advances", async () => {
    // A server bug, not a reachable state — but an infinite fetch loop in a
    // panel is worse than a short record, and a short record says so.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => envelope(page([1], 1), 999),
      }))
    );
    const history = await getGoalHistory(1);
    expect(history.complete).toBe(false);
    expect(globalThis.fetch).toHaveBeenCalledTimes(201);
  });
});
