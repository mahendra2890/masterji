/** How a place on the cohort board is written.
 *
 * In `lib/` rather than in the component because it is the one piece of the
 * board with a rule in it, and rules are the part worth testing. Everything
 * else on that page is a number the server sent, rendered.
 *
 * The rank itself is ALWAYS the server's. Ties share a place — two builders on
 * identical counts are both 2nd, and the next is 4th — so a client that
 * numbered the list by its own index would silently break that, and it would
 * look right on any fixture without a tie in it.
 */
export function place(rank: number): string {
  // 11th, 12th, 13th, and 111th–113th. The exception that every ordinal
  // helper written from the last digit alone gets wrong.
  const tens = rank % 100;
  if (tens >= 11 && tens <= 13) return `${rank}th`;
  return `${rank}${["th", "st", "nd", "rd"][rank % 10] ?? "th"}`;
}
