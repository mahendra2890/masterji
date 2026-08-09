import type { Metadata } from "next";
import Tour from "./Tour";

export const metadata: Metadata = {
  title: "How Masterji works — a guided tour",
  description:
    "Nine steps through the real product: commit one goal, declare a task " +
    "each morning, file proof each evening, and a phase gate the coach " +
    "himself can't open.",
};

export default function DemoPage() {
  return <Tour />;
}
