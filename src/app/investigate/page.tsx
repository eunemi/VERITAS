import type { Metadata } from "next";
import { CommissionBench } from "./CommissionBench";

export const metadata: Metadata = {
  title: "Open an investigation",
  description:
    "Hand over one artifact — copy, a frame, a recording or footage — and every desk that can read it files a record on it.",
};

/**
 * The commission bench sits in a client component so this route can still carry
 * its own metadata: the bench holds the artifact and the filed records in state,
 * and metadata cannot be exported from a client module.
 */
export default function InvestigatePage() {
  return <CommissionBench />;
}
