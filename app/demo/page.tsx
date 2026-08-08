import type { Metadata } from "next";
import Link from "next/link";
import Changelog from "@/components/Changelog";
import app from "../masterji.module.css";
import styles from "./demo.module.css";

export const metadata: Metadata = {
  title: "Demo — Masterji",
  description:
    "A canned look at Masterji: the phase gate refusing a builder who wants " +
    "to talk tech stacks before talking to customers.",
};

const MESSAGES = [
  {
    role: "COACH",
    content:
      'Goal locked: "Tiffin-delivery app for my college". You are in VALIDATION — conversations, not code. 2 of 3 proofs banked. Finish the third.',
  },
  {
    role: "USER",
    content: "Quick one — should I build this in Next.js or Remix? And Postgres or Mongo?",
  },
  {
    role: "COACH",
    content:
      "Fair question, wrong week. Both of those are BUILD's problem, and neither answer survives a user you haven't met — you have one conversation left before BUILD unlocks. The Mom Test says talk about their life, not your idea: go ask the hostel mess aunty what she does when orders pile up. Bring me notes tonight.",
  },
  { role: "USER", content: "Fine. Can we at least move to BUILD? I feel ready." },
  {
    role: "COACH",
    content:
      "Ready isn't the thing I count — let me check the ledger…\n\nNot yet. 2/3 accepted proofs in VALIDATION — 1 more before BUILD unlocks. One conversation. Ten minutes, someone who already has the problem. Ask what they did the last time it happened — not whether they'd use your app. Notes tonight.",
  },
  {
    role: "USER",
    content:
      "Talked to the mess aunty. Says the 9pm rush is 40 plates in 20 minutes and she just stops taking orders.",
  },
  {
    role: "COACH",
    content:
      '"She just stops taking orders" — that\'s the workaround, and it\'s the part most builders never reach. That clears the bar, so I\'ve written it up as tonight\'s proof. Check it on the left and file it; you don\'t have to say it again in my words.',
  },
] as const;

// What Masterji drafted from that last exchange, sitting on the check-in
// waiting to be filed. In the product this arrives from the suggest_proof
// tool call; here it is the same copy, so the demo shows the thing rather
// than describing it.
const DRAFT =
  "Spoke to the mess aunty about the 9pm rush. She gets around 40 plates " +
  "of orders inside 20 minutes and can't cook that fast, so she stops " +
  "taking orders — she doesn't turn people away, she just goes quiet. " +
  "That's the workaround today.";

const HISTORY = [
  { date: "08-04", text: "Interview 2 hostel students about tiffin orders", ok: "✓" },
  { date: "08-03", text: "Talk to the mess contractor about delivery slots", ok: "✓" },
  { date: "08-02", text: "Make a feature list and moodboard", ok: "✗" },
] as const;

export default function DemoPage() {
  return (
    <main className={app.app}>
      <div className={styles.banner}>
        This is a canned demo — the gate refusals you see are real product
        behavior, enforced by the server. Everything he judges by is public:{" "}
        <a
          href="https://github.com/mahendra2890/masterji/tree/main/backend/coach/playbooks"
          target="_blank"
          rel="noreferrer"
        >
          read the method
        </a>{" "}
        in ten minutes. <Link href="/login/">Sign in</Link> to get your own
        Masterji.
      </div>

      <header className={app.header}>
        <span className={app.brand}>
          Masterji <span className={app.brandHindi}>मास्टरजी</span>
        </span>
        <div className={app.headerRight}>
          <span className={app.streak}>4 days 🔥</span>
          <Changelog />
          <Link className={styles.cta} href="/login/">
            Start yours →
          </Link>
        </div>
      </header>

      <div className={app.columns}>
        <aside className={app.side}>
          <section className={app.card}>
            <p className={app.cardLabel}>The goal</p>
            <h2 className={app.goalTitle}>Tiffin-delivery app for my college</h2>
            <ol className={app.stepper}>
              <li className={app.stepDone}>IDEA</li>
              <li className={app.stepNow}>VALIDATION</li>
              <li className={app.stepTodo}>BUILD</li>
              <li className={app.stepTodo}>LAUNCH</li>
            </ol>
            <p className={app.phaseHint}>
              Talk to real customers. Bring notes, not opinions.
            </p>
            <div className={app.gateRow}>
              <span>
                <strong>2</strong>/3 proofs toward BUILD
              </span>
            </div>
            <div className={app.gateBar}>
              <div className={app.gateFill} style={{ width: "66%" }} />
            </div>
            <p className={app.gateNote}>
              Not yet. 2/3 accepted proofs in VALIDATION — 1 more before BUILD
              unlocks. One conversation. Ten minutes, someone who already has
              the problem.
            </p>
          </section>

          <section className={app.card}>
            <p className={app.cardLabel}>Today</p>
            <p className={app.declared}>
              Declared: <em>Interview the mess aunty about peak-hour orders</em>
            </p>
            <div className={app.proofOffer}>
              <p className={app.proofOfferLabel}>
                Masterji wrote this from your conversation
              </p>
              <p className={app.proofOfferText}>{DRAFT}</p>
              <p className={styles.draftNote}>
                Filed as he wrote it, it goes straight through — he already
                decided it counted.
              </p>
            </div>
            <p className={app.pushedBack}>
              Proof still owed tonight. Masterji is watching the clock.
            </p>
          </section>

          <section className={app.card}>
            <p className={app.cardLabel}>The record</p>
            <ul className={app.history}>
              {HISTORY.map((h) => (
                <li key={h.date} className={app.historyRow}>
                  <span className={app.historyDate}>{h.date}</span>
                  <span className={app.historyText}>{h.text}</span>
                  <span className={h.ok === "✓" ? app.chipGood : app.chipBad}>
                    {h.ok}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </aside>

        <section className={app.chat}>
          <div className={app.messages}>
            {MESSAGES.map((m, i) => (
              <div key={i} className={m.role === "COACH" ? app.coachMsg : app.userMsg}>
                {m.role === "COACH" && <span className={app.avatar}>म</span>}
                <p className={app.msgBody}>{m.content}</p>
              </div>
            ))}
          </div>
          <div className={app.composer}>
            {/* The real control, in the real place, wearing the app's own
                classes. A reader who never signs in should still leave
                knowing Masterji has two ways of talking — the demo is where
                most people meet this product, and the mode was invisible
                here for as long as it was a word in the corner of a header
                the demo doesn't even render. Inert, like the box below it. */}
            <div className={app.modeBar}>
              <div
                className={app.modeSwitch}
                role="group"
                aria-label="How Masterji talks to you"
              >
                <span className={app.modeOptOn}>Coach me</span>
                <span className={app.modeOpt}>Think with me</span>
              </div>
              <p className={app.modeCaption}>
                One task, proof tonight. Switch before there&rsquo;s anything to
                declare.
              </p>
            </div>
            <div className={app.composerRow}>
              <textarea
                className={app.composerInput}
                rows={1}
                disabled
                placeholder="Sign in to talk to Masterji…"
              />
              <Link
                href="/login/"
                className={app.primaryBtn}
                style={{ textDecoration: "none" }}
              >
                Sign in
              </Link>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
