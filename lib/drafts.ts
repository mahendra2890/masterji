// Drafts that survive the tab.
//
// Lifted out of Masterji.tsx unchanged. They were private to that file, which
// meant the rules below — an expiry, a shape check against a value the builder
// can hand-edit, and two failure paths that must stay silent — could only be
// exercised by driving a browser eighteen hours into the future with a
// localStorage that throws. They are arithmetic over a key, a timestamp and a
// string, and they are what decides whether an evening's typing comes back.
//
// The hook that uses them stays in Masterji.tsx: its rules are about renders
// (restore once per key, only into an empty box), and asserting those would
// need a DOM. #117 decided against having one, so those rules are verified by
// driving the app rather than left waiting for a harness that is not coming.

export const DRAFT_PREFIX = "masterji.draft.";

/** How long a saved draft stays worth putting back.
 *
 * Not a calendar-day comparison, on purpose. A proof typed at 23:55 and
 * finished at 00:05 is one evening's work — the server already agrees, since
 * the night-owl rule files it against the declaration's own day — and a rule
 * that dropped it at midnight would fail the exact builder this app is for.
 * Long enough to cover dinner, a lab, and a phone that discarded the tab in
 * between; short enough that a paragraph from last week never reappears
 * underneath tonight's task, which is worse than losing it. */
export const DRAFT_MAX_AGE_MS = 18 * 60 * 60 * 1000;

/** A draft as it is stored: the words, and when they were last typed. */
type StoredDraft = { v: string; at: number };

/** Every read is wrapped, and a failure is always "no draft".
 *
 * localStorage is not a guarantee. Safari in private browsing throws on
 * access, a full quota throws on write, and the value itself is a string a
 * user can edit by hand. None of that may reach the builder: the worst this
 * feature is allowed to do is what the product does today, which is forget. */
export function readDraft(key: string): string {
  try {
    const raw = window.localStorage.getItem(DRAFT_PREFIX + key);
    if (!raw) return "";
    const { v, at } = JSON.parse(raw) as Partial<StoredDraft>;
    if (typeof v !== "string" || typeof at !== "number") return "";
    if (Date.now() - at > DRAFT_MAX_AGE_MS) {
      window.localStorage.removeItem(DRAFT_PREFIX + key);
      return "";
    }
    return v;
  } catch {
    return "";
  }
}

export function writeDraft(key: string, value: string) {
  try {
    if (value) {
      const stored: StoredDraft = { v: value, at: Date.now() };
      window.localStorage.setItem(DRAFT_PREFIX + key, JSON.stringify(stored));
    } else {
      window.localStorage.removeItem(DRAFT_PREFIX + key);
    }
  } catch {
    // A quota that's full costs the draft, never the evening.
  }
}
