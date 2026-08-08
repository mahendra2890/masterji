import type { Metadata } from "next";
import Tour from "./Tour";

export const metadata: Metadata = {
  title: "How Masterji works — a guided tour",
  description:
    "Eight steps through the real product: declare a task each morning, " +
    "file proof each evening, and a phase gate the coach himself can't open.",
};

export default function DemoPage() {
  return <Tour />;
}
