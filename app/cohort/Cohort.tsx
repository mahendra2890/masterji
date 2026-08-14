"use client";

// Your cohort's board: what forty builders actually banked, ranked on counts
// the server made.
//
// The field this is arguing with runs on jury-judged self-reports and pitch
// milestones — NEC, NSRCEL — so the loudest deck wins. There is no field on
// this page a deck could be written in. Every column is a server count that
// came through a gate: accepted proofs, the subset that needed a real person,
// the current streak, the phase reached. No goal titles, no proof text, no
// email addresses, nothing anybody typed about themselves.
//
// READ-ONLY ABOUT THE RECORD, and completely. Nothing reachable from this page
// can bank or unbank a proof, move a phase, or touch another builder's row —
// the board endpoint is GET and defines no other verb at all. The two controls
// here write exactly one thing between them, the reader's OWN membership:
// joining by code, which is the consent itself, and leaving, which withdraws
// it. Neither can name anybody else. See coach/cohorts.py.

import { useCallback, useEffect, useState } from "react";
import AuthGate from "@/components/AuthGate";
import {
  ApiError,
  getCohortBoard,
  getCohorts,
  joinCohort,
  leaveCohort,
  type Cohort as Cohort_,
  type CohortRow,
} from "@/lib/coach-api";
import { place } from "@/lib/cohort";
import styles from "./cohort.module.css";

type Board = { cohort: Cohort_; rows: CohortRow[] };

function Row({ row }: { row: CohortRow }) {
  if (!row.hasGoal) {
    return (
      <li className={`${styles.row} ${styles.idle}`}>
        <span className={styles.place} aria-hidden="true">
          —
        </span>
        <span className={styles.who}>{row.name}</span>
        {/* Not ranked, and not hidden either. Between ideas is a real state and
            a board that scored it 0 would be making a judgement out of an
            absence. */}
        <span className={styles.between}>between ideas</span>
      </li>
    );
  }
  return (
    <li className={styles.row}>
      <span className={styles.place}>{row.rank === null ? "—" : place(row.rank)}</span>
      <span className={styles.who}>{row.name}</span>
      <span className={styles.phase}>{row.phase}</span>
      {/* Contact proofs lead because they are the coordinator's actual question
          — which of these forty talked to somebody — and every one of them
          cleared a gate stamped VALIDATION or later. */}
      <span className={styles.figure}>
        <span className={styles.figureValue}>{row.contactProofs}</span>
        <span className={styles.figureLabel}>from real contact</span>
      </span>
      <span className={styles.figure}>
        <span className={styles.figureValue}>{row.acceptedProofs}</span>
        <span className={styles.figureLabel}>proofs banked</span>
      </span>
      <span className={styles.figure}>
        <span className={styles.figureValue}>{row.streak}</span>
        <span className={styles.figureLabel}>day streak</span>
      </span>
    </li>
  );
}

function Board({ board, onLeave }: { board: Board; onLeave: (id: number) => void }) {
  const [confirming, setConfirming] = useState(false);
  const { cohort, rows } = board;

  return (
    <section className={styles.board}>
      <header className={styles.boardHead}>
        <h2 className={styles.boardName}>{cohort.name}</h2>
        <span className={styles.size}>
          {cohort.members} {cohort.members === 1 ? "builder" : "builders"}
        </span>
      </header>

      {rows.length === 0 ? (
        <p className={styles.empty}>Nobody has joined yet.</p>
      ) : (
        <ol className={styles.rows}>
          {rows.map((row) => (
            <Row key={row.name} row={row} />
          ))}
        </ol>
      )}

      {/* Leaving is the only thing on this page that changes anything, and what
          it changes is one row: this reader's membership. Said in full before
          it fires, because "what happens to my record" is the question worth
          answering here and the answer is nothing. */}
      {confirming ? (
        <p className={styles.leaveBox}>
          Leave {cohort.name}? Your row goes off this board. Every goal,
          evening and proof you have stays exactly as it is — your record does
          not know this cohort exists.{" "}
          <button className={styles.leaveYes} onClick={() => onLeave(cohort.id)}>
            Leave
          </button>{" "}
          <button className={styles.leaveNo} onClick={() => setConfirming(false)}>
            Stay
          </button>
        </p>
      ) : (
        <button className={styles.leave} onClick={() => setConfirming(true)}>
          Leave this cohort
        </button>
      )}
    </section>
  );
}

function Cohorts() {
  const [boards, setBoards] = useState<Board[] | null>(null);
  const [code, setCode] = useState("");
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const cohorts = await getCohorts();
    // One request per cohort, and that is not the N+1 this feature worried
    // about: a builder is in one cohort, occasionally two. The forty-member
    // fan-out is inside each board, and the server does that in four queries
    // whatever the size.
    const loaded = await Promise.all(
      cohorts.map(async (c) => {
        const { cohort, board } = await getCohortBoard(c.id);
        return { cohort, rows: board };
      })
    );
    setBoards(loaded);
  }, []);

  useEffect(() => {
    load().catch(() => setBoards([]));
  }, [load]);

  async function join(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim() || joining) return;
    setJoining(true);
    setError("");
    try {
      await joinCohort(code);
      setCode("");
      await load();
    } catch (err) {
      // The server's own sentence — "No cohort with that code." — rather than a
      // status code translated back into English here.
      setError(err instanceof ApiError ? err.message : "Couldn't reach Masterji.");
    } finally {
      setJoining(false);
    }
  }

  async function leave(id: number) {
    await leaveCohort(id).catch(() => {});
    await load().catch(() => {});
  }

  return (
    <main className={styles.page}>
      <p className={styles.wordmark}>मास्टरजी</p>
      <h1 className={styles.title}>Your cohort</h1>
      <p className={styles.standfirst}>
        Ranked on what the server counted, not on what anybody said about
        themselves. Every proof below was filed on an evening and had to be
        accepted before it counted.
      </p>

      {boards === null ? (
        <p className={styles.quiet}>Reading the board…</p>
      ) : (
        boards.map((board) => (
          <Board key={board.cohort.id} board={board} onLeave={leave} />
        ))
      )}

      {/* The join box. This is where consent is given, which is why it says
          what joining means before it is pressed rather than in a footnote
          under it. */}
      <form className={styles.join} onSubmit={join}>
        <label className={styles.joinLabel} htmlFor="cohort-code">
          {boards?.length ? "Join another cohort" : "Join a cohort"}
        </label>
        <p className={styles.joinNote}>
          Your E-Cell gives you a code. Joining puts your counts — proofs
          banked, conversations with real people, your streak — on their board
          where the others can see them. It shows nothing you wrote: not your
          idea, not a proof, not your email. You can leave whenever you like,
          and your record is unchanged either way.
        </p>
        <span className={styles.joinRow}>
          <input
            id="cohort-code"
            className={styles.code}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="ABCD2345"
            autoComplete="off"
            spellCheck={false}
            maxLength={32}
          />
          <button className={styles.joinGo} disabled={!code.trim() || joining}>
            {joining ? "Joining…" : "Join"}
          </button>
        </span>
        {error ? <p className={styles.error}>{error}</p> : null}
      </form>

      <p className={styles.footnote}>
        Nobody running a cohort can change what is on this page. There is no
        button for it anywhere, and the endpoint it reads has no way to write —
        a coordinator can see the record and cannot touch it. That is the whole
        difference between this and a leaderboard of self-reports.{" "}
        <a className={styles.link} href="/">
          Back to Masterji
        </a>
      </p>
    </main>
  );
}

export default function Cohort() {
  // Signed-in only, and deliberately with NO `signedOut` page. A cohort board
  // is somebody's work shown to the peers they agreed to show it to, so there
  // is no version of it for a stranger — and AuthGate reads the absence as
  // "send them to / with a ?next", which lands them back here once they are in.
  return <AuthGate firstPaint="app">{() => <Cohorts />}</AuthGate>;
}
