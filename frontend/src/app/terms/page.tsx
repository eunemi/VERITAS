import type { Metadata } from "next";
import Link from "next/link";
import { StatementPage, type Clause } from "@/components/ui/StatementPage";

export const metadata: Metadata = {
  title: "Terms of use",
  description:
    "What Veritas is, what a determination means, and what you agree to by submitting an artifact.",
};

const CLAUSES: Clause[] = [
  {
    heading: "What this site is",
    body: (
      <>
        <p>
          Veritas is a verification service in active development. It accepts text, documents, images
          and public page URLs, sends them to the configured examination backend, and returns source
          records and model-assisted determinations. The service is not a substitute for editorial,
          legal, medical, financial or other professional judgment.
        </p>
      </>
    ),
  },
  {
    heading: "What a determination is worth",
    body: (
      <>
        <p>
          A determination is an evidence summary and an assessment produced by the configured desks;
          it is not a guarantee, certification, or calibrated probability. Sources can be incomplete,
          inaccessible, wrong, or later corrected. Review the cited evidence yourself before
          publishing, making a consequential decision, or treating a result as proof of authenticity
          or fabrication.
        </p>
      </>
    ),
  },
  {
    heading: "What you may submit",
    body: (
      <>
        <p>
          Only material you hold the rights to, or are otherwise entitled to have examined. Do not
          submit anything unlawful, and do not submit anything containing another person&rsquo;s
           private information that you have no right to circulate. The bench sends what you hand it
           to the verification service — see{" "}
          <Link
            href="/privacy"
            className="border-b border-secondary transition-colors hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
          >
            what we keep
          </Link>{" "}
          — but that is a description of the software, not permission to submit material you should
          not have.
        </p>
      </>
    ),
  },
  {
    heading: "The reporting on this site",
    body: (
      <>
        <p>
          The stories on the world, economy and technology pages and the records on the public index
          are editorial examples. They may name real places or institutions in illustrative
          circumstances and are not user submissions, live monitoring, or journalism. Do not quote
          them as reports of events that happened.
        </p>
      </>
    ),
  },
  {
    heading: "No warranty",
    body: (
      <>
        <p>
          The site is provided as it is, with no warranty of accuracy, availability or fitness for
          any purpose, and with no liability for anything done or not done on the strength of what it
          prints. That is stated here so no reader has to infer it.
        </p>
      </>
    ),
  },
];

export default function TermsPage() {
  return (
    <StatementPage
      kicker="Terms"
      titleLines={["The terms", "you read this under."]}
      standfirst="The service states what a determination means here, and where its limits are."
      clauses={CLAUSES}
      foot={
        <>
          These terms describe the current service and its limitations. The{" "}
          <Link
            href="/intel"
            className="border-b border-ink-black/30 transition-colors hover:text-secondary"
          >
            register of desks
          </Link>{" "}
          states, desk by desk, what each one will read and what it will refuse to rule on.
        </>
      }
    />
  );
}
