"use client";

import { useState } from "react";
import { EXPORT_MIME, exportGoal } from "@/lib/coach-api";
import { saveTextFile } from "@/lib/download";
import styles from "@/app/masterji.module.css";

/** Downloads a goal's whole record as a file.
 *
 * A component rather than a hook because both callers want the same three
 * states in the same words: the closed-idea drill-in, where the record has just
 * become a thing the builder keeps rather than uses, and the live goal card,
 * because the artifact is most wanted while the work is still going on — an
 * E-Cell application or an interview does not wait for the idea to end.
 *
 * Borrowed pixels: `moreDays` is the small underlined action the record card
 * already uses, and this is the same kind of thing — a way to ask for more of
 * what you are already looking at.
 */
export default function TakeTheRecord({
  goalId,
  label = "Take this record with you",
}: {
  goalId: number;
  label?: string;
}) {
  const [state, setState] = useState<"idle" | "working" | "failed">("idle");

  async function save() {
    setState("working");
    try {
      const { filename, text } = await exportGoal(goalId);
      saveTextFile(filename, text, EXPORT_MIME);
      setState("idle");
    } catch {
      // Named, not swallowed. The record is the thing this product argues is
      // worth having; failing to hand it over silently would be the one failure
      // mode that looks exactly like success.
      setState("failed");
    }
  }

  return (
    <button
      className={styles.moreDays}
      onClick={save}
      disabled={state === "working"}
    >
      {state === "working"
        ? "Preparing…"
        : state === "failed"
          ? "Couldn't build the file — try again"
          : label}
    </button>
  );
}
