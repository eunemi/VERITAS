import type { Metadata } from "next";
import Link from "next/link";
import { StatementPage, type Clause } from "@/components/ui/StatementPage";

export const metadata: Metadata = {
  title: "What we keep",
  description:
    "What happens to an artifact you hand Veritas, what is stored, and which services process a verification.",
};

/**
 * The privacy note.
 *
 * Written against the current service rather than against a prototype template.
 * Submissions are sent to the separate verification API, which may call the
 * providers configured for the deployment. The public archive remains editorial
 * example content; signed-in records belong to the account that filed them.
 */
const CLAUSES: Clause[] = [
  {
    heading: "What you hand over",
    body: (
      <>
        <p>
          The bench accepts pasted copy or a single claim, a still image, a DOCX or PDF document, or
          a public page URL. An account is optional. When you sign in, the record is attached to your
          account; when you do not, the record is anonymous and its returned file number is the handle
          used to read it.
        </p>
      </>
    ),
  },
  {
    heading: "Where it is read",
    body: (
      <>
        <p>
          A submission is sent to the separate FastAPI verification service. Text and document files
          are read there, public URLs and image URLs are fetched there, and uploaded images are stored
          behind an API-served file URL before examination. The service may send the material needed
          for the selected desk to the language-model, search, fact-check or vision providers enabled
          by that deployment. Their own terms and retention policies apply to those requests.
        </p>
      </>
    ),
  },
  {
    heading: "What the desks report",
    body: (
      <>
        <p>
          Desk records contain the evidence returned by the configured research providers, the source
          excerpts selected by the examination, and a determination and confidence produced by the
          verification graph. A configured language model may assist with claim extraction, semantic
          reasoning, observations or the written explanation; fallbacks can return an insufficient
          result when that assistance is unavailable. Confidence is an estimate, not a calibrated
          probability or a guarantee of truth. An image result does not certify the photograph&rsquo;s
          original capture, pixel history, or authorship.
        </p>
      </>
    ),
  },
  {
    heading: "What is stored",
    body: (
      <>
        <p>
          Signed-in accounts store an email address, display name, password hash and account timestamps.
          Verifications store the submitted artifact reference or text, desk progress, reports,
          evidence, timestamps and optional account ownership. Uploaded images are written to the
          backend&rsquo;s configured upload directory. The production service uses PostgreSQL by default;
          local memory mode is non-durable. There is currently no self-service deletion endpoint, so
          do not submit material that requires a guaranteed deletion workflow. No scheduled deletion
          policy is implemented by the current service; records and uploaded images remain until the
          deployment&rsquo;s operator, database, or storage retention policy removes them. The frontend has
          no analytics script or third-party tracking tag.
        </p>
      </>
    ),
  },
  {
    heading: "The archive",
    body: (
      <>
        <p>
          The records on{" "}
          <Link
            href="/archive"
            className="border-b border-secondary transition-colors hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
          >
            the index
          </Link>{" "}
          are published examples written for the public site, not a public feed of user submissions.
          Records you commission while signed in appear only in your private file. Anonymous records
          remain readable through the returned file number, but are not added to the public index.
        </p>
      </>
    ),
  },
  {
    heading: "When this changes",
    body: (
      <>
        <p>
          Provider, storage, account or deletion behavior can change by deployment. This page should
          be updated before a material change goes live, with the destination of each submission, the
          services that process it, the retention behavior, and the available deletion path.
        </p>
      </>
    ),
  },
];

export default function PrivacyPage() {
  return (
    <StatementPage
      kicker="Privacy"
      titleLines={["What we keep", "of what you hand us."]}
       standfirst="A submission leaves the browser for the verification service. Here is what the current system stores and sends, plainly."
      clauses={CLAUSES}
      foot={
        <>
          This note describes the current frontend and backend configuration, not every provider&rsquo;s
          separate policy. If a deployment changes where submissions are processed, how long records
          are retained, or whether deletion is available, this page must be revised before that
          deployment accepts new artifacts.
        </>
      }
    />
  );
}
