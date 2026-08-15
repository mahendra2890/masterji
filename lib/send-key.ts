/** Whether the return key should send the reply, or make a line.
 *
 * "Enter sends, Shift+Enter breaks the line" is a hardware-keyboard bargain,
 * and a soft keyboard can't hold up its end: there is no Shift to hold, so
 * the only newline key a phone has was the send button. Tapping the ⏎ icon —
 * which draws itself as a line break, and is the one key there for starting a
 * paragraph — fired the reply off half-written. What gets typed in that box is
 * a night's thinking, so a second paragraph is the normal case, not an edge
 * one, and losing the first one to a keystroke costs the builder the whole
 * point of the box.
 *
 * So ask for the hardware instead of guessing at the screen: a pointer that
 * is fine and hovers is a mouse or a trackpad, and a device driven by one has
 * a Shift key to pair with Enter. Everywhere else the return key does what
 * its icon says and Send is what sends — which is the only affordance a phone
 * had all along. Deliberately not a width test: a desktop window dragged
 * narrow still has the keyboard, and a tablet held wide still doesn't.
 *
 * Asked at the keypress rather than read once at mount, which costs nothing at
 * this rate and means there is no matchMedia call during SSR, no state to
 * hydrate, and no stale answer for an iPad that has since been put in a
 * keyboard case.
 */
const enterSends = () =>
  window.matchMedia("(hover: hover) and (pointer: fine)").matches;

/** Whether this keystroke means send, in either of the two boxes that talk to
 * Masterji.
 *
 * One predicate because both used to spell the condition out, and the
 * workshop's copy was missing the `enterSends()` half — so on a phone the room
 * fired a half-written turn where the chat inserted a newline. That is worse in
 * the room than it would be in the chat: a workshop turn is metered
 * (views.WORKSHOP_TURNS), the row is written before the model is called, and
 * the coach's opening move there is to ask for a walk through the builder's
 * last seven days, which is a multi-paragraph answer by design.
 *
 * Lives in lib/ rather than beside one of its two callers: the room is its own
 * module now, and the predicate the two boxes share cannot sit inside either
 * of them without one importing the other.
 *
 * Takes the fields it reads rather than a React event, so a third box cannot
 * diverge by copying four fifths of the condition again. */
export const isSendKey = (e: { key: string; shiftKey: boolean }) =>
  e.key === "Enter" && !e.shiftKey && enterSends();
