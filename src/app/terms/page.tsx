import type { Metadata } from "next";
import Link from "next/link";
import { StatementPage, type Clause } from "@/components/ui/StatementPage";

export const metadata: Metadata = {
  title: "Terms of use",
  description:
    "What Veritas is, what a determination is worth while the examination model is not attached, and what you agree to by submitting an artifact.",
};

const CLAUSES: Clause[] = [
  {
    heading: "What this site is",
    body: (
      <>
        <p>
          Veritas is a working prototype of a verification desk. The layout, the routing between
          desks and the shape of every record are real; the examination behind them is not attached
          yet. Read the site as a demonstration of how a determination would be reported, not as a
          service that determines anything.
        </p>
      </>
    ),
  },
  {
    heading: "What a determination is worth",
    body: (
      <>
        <p>
          Nothing, for now. Every finding, figure, confidence and signed determination on this site
          is a fixture. Do not publish, cite, or act on one, and do not present a record from this
          site as evidence that a piece of material is authentic or fabricated. When the model is
          attached, this clause is the first one that will change.
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
          private information that you have no right to circulate. The bench reads what you hand it
          in your browser — see{" "}
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
          The stories on the world, economy and technology pages, and the records on the index, are
          written to populate the design. They name real places and institutions in invented
          circumstances, and none of them is journalism. Nothing on those pages should be quoted as a
          report of an event that happened.
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
          prints. That is the ordinary position for a prototype, and it is stated here so no reader
          has to infer it.
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
      standfirst="A prototype should say so on its own terms page. This one does, and it says what a determination here is worth."
      clauses={CLAUSES}
      foot={
        <>
          These terms describe a prototype in development and will be replaced before anything on
          this site is offered as a verification service. Until then, treat every record as a
          specimen of layout — the{" "}
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
