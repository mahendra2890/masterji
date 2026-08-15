// What the record's rows say about themselves, computed from the rows.
//
// Both facts here were read off the wrong source. A row is identified on
// screen by its date alone, and a day may hold more than one declare→prove
// cycle — CheckIn's docstring: "a builder who genuinely does more in a day may
// run more cycles" — so two rows of one day render identically. And the phase
// drill-in's heading came from the transition timestamps while its list came
// from each row's stamped phase: two clocks, no reconciliation, and the label
// is the half a reader trusts because it looks like a summary of the list.
//
// Pure and separate for the reason #117 settled: this is decidable arithmetic
// over data the payload already holds, so it is pinned here, and the two lines
// of JSX that render the answer are driven in a browser.

export type Cycle = { id: number; date: string };

/** Which cycle of its own day each row is: 1 for a day's first filing, and for
 * every day that holds only one; 2 and up for the repeats.
 *
 * Keyed on `id`, and ordered by it. `CheckIn.Meta.ordering` is `["-date"]`
 * alone, so rows within a single date arrive in whatever order the database
 * returns — position in the payload is not the cycle order and must not be
 * counted as it. `id` is the insertion sequence, which is the order the cycles
 * were actually run in.
 *
 * Call this over the WHOLE row set the caller holds, never over a filtered
 * slice. The sidebar record and the phase drill-in show overlapping subsets of
 * the same rows, and a row that is the 2nd cycle in one of them cannot be the
 * 1st in the other.
 */
export function cycleOrdinals(rows: readonly Cycle[]): Map<number, number> {
  const byDate = new Map<string, number[]>();
  for (const row of rows) {
    const ids = byDate.get(row.date);
    if (ids) ids.push(row.id);
    else byDate.set(row.date, [row.id]);
  }
  const ordinals = new Map<number, number>();
  for (const ids of byDate.values()) {
    ids.sort((a, b) => a - b);
    ids.forEach((id, i) => ordinals.set(id, i + 1));
  }
  return ordinals;
}

/** The record's own order — newest first — carried inside a date as well as
 * across dates.
 *
 * The server orders by `-date` alone, so a day's cycles come back in no
 * particular order, and until they were numbered nobody could see it. Numbered,
 * they read "4th, 1st, 2nd, 3rd" down a card whose stated rule is most recent
 * first. Sorting by `id` descending inside the date is that rule applied one
 * level further down, and it uses the same insertion sequence the ordinals are
 * counted from, so the marker and the order can never disagree.
 *
 * A copy, not a sort in place: the caller's array is state.
 */
export function newestFirst<T extends Cycle>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => (a.date === b.date ? b.id - a.id : a.date < b.date ? 1 : -1));
}

/** Whether the cycle column is worth drawing over a set of rows.
 *
 * The marker is a narrow column beside the date, and on the ordinary record —
 * one cycle a day, every row reading "1st" — it is a column of the same word
 * repeated, which says nothing and costs width on a 360px phone. Drawn only
 * when a day in view was actually run twice.
 *
 * Asked per rendered set, not per goal: the record card and the phase drill-in
 * show overlapping subsets, and a repeat outside the rows on screen is not
 * something the reader can see. Takes the ordinals computed over the WHOLE row
 * set (see `cycleOrdinals`) so the two answers cannot disagree about which
 * cycle a row is.
 */
export function anyRepeat(
  rows: readonly Cycle[],
  ordinals: Map<number, number>,
): boolean {
  return rows.some((row) => (ordinals.get(row.id) ?? 1) > 1);
}

/** What the record card shows: newest first, the last `preview` rows until the
 * reader asks for the rest, and whether the cycle column comes with them.
 *
 * `preview` counts ROWS, not days. A builder who declares a second task after
 * proving the first gets two rows for one date, and the card would rather show
 * seven rows than promise seven days and count them wrong.
 *
 * `showCycle` is decided over the rows actually shown, never over all of them:
 * a day run twice three months ago should not put an empty-looking column
 * beside this week.
 */
export function recordSlice<T extends Cycle>(
  rows: readonly T[],
  ordinals: Map<number, number>,
  expanded: boolean,
  preview: number,
): { shown: T[]; showCycle: boolean } {
  const ordered = newestFirst(rows);
  const shown = expanded ? ordered : ordered.slice(0, preview);
  return { shown, showCycle: anyRepeat(shown, ordinals) };
}

const SUFFIXES = ["th", "st", "nd", "rd"];

/** "1st", "2nd", "3rd", "4th" — for a marker that sits in a narrow column
 * beside the date, where "cycle 2" would not fit and "2" alone reads as a
 * count of something.
 *
 * The teens are the case a naive version gets wrong (11th, not 11st). Reached
 * only by a builder who files eleven cycles in one day, which the model
 * permits and this therefore has to survive.
 */
export function ordinalLabel(n: number): string {
  const teens = n % 100;
  const suffix = teens >= 11 && teens <= 13 ? "th" : (SUFFIXES[n % 10] ?? "th");
  return `${n}${suffix}`;
}

export type Extent = {
  /** Earliest and latest `CheckIn.date` in the list — the client's local
   * dates, the same clock the rows are rendered on. */
  start: string;
  end: string;
  /** Distinct dates, and rows. They differ exactly when a day was run twice,
   * which is why a heading over these rows cannot call its rows "days". */
  days: number;
  cycles: number;
};

/** What a list of rows spans, taken from the rows themselves.
 *
 * `null` for an empty list rather than a zero-width range: a caller with no
 * rows has nothing to summarise and should say so instead of printing a date.
 *
 * Compared as strings, which is exact for these and not a shortcut worth
 * removing: `CheckIn.date` is a fixed-width "YYYY-MM-DD", so lexicographic
 * order is chronological order, and parsing to Date objects here would be a
 * second place in the app where a bare date meets a timezone.
 */
export function rowsExtent(rows: readonly { date: string }[]): Extent | null {
  if (rows.length === 0) return null;
  const dates = new Set<string>();
  let start = rows[0].date;
  let end = rows[0].date;
  for (const row of rows) {
    dates.add(row.date);
    if (row.date < start) start = row.date;
    if (row.date > end) end = row.date;
  }
  return { start, end, days: dates.size, cycles: rows.length };
}
