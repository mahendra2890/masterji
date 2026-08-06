import type { Metadata } from "next";
import Link from "next/link";
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
      "No. You have zero users and one conversation left before BUILD unlocks — framework talk is procrastination wearing a hard hat. The Mom Test says talk about their life, not your idea: go ask the hostel mess aunty what she does when orders pile up. Bring me notes tonight.",
  },
  { role: "USER", content: "Fine. Can we at least move to BUILD? I feel ready." },
  {
    role: "COACH",
    content:
      "Feelings aren't proofs. Let me check the ledger…\n\nNot yet. 2/3 accepted proofs in VALIDATION — 1 more before BUILD unlocks. One conversation. Ten minutes, someone who already has the problem. Ask what they did the last time it happened — not whether they'd use your app. Notes tonight.",
  },
] as const;

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
        behavior, enforced by the server. <Link href="/login/">Sign in</Link>{" "}
        to get your own Masterji.
      </div>

      <header className={app.header}>
        <span className={app.brand}>
          Masterji <span className={app.brandHindi}>मास्टरजी</span>
        </span>
        <div className={app.headerRight}>
          <span className={app.streak}>4 days 🔥</span>
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
            <textarea
              className={app.composerInput}
              rows={1}
              disabled
              placeholder="Sign in to talk to Masterji…"
            />
            <Link href="/login/" className={app.primaryBtn} style={{ textDecoration: "none" }}>
              Sign in
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
