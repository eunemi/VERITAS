import type { Metadata } from "next";
import Link from "next/link";
import { StatementPage, type Clause } from "@/components/ui/StatementPage";

export const metadata: Metadata = {
  title: "What we keep",
  description:
    "What happens to an artifact you hand Veritas, what is stored, and what changes when the examination model is attached.",
};

/**
 * The privacy note.
 *
 * Written against what the code actually does today rather than against a
 * template: there is no examination model attached, so an artifact is read in the
 * browser and never sent anywhere. Every clause here has to be re-read the day a
 * backend is added — clause 06 says so in the open.
 */
const CLAUSES: Clause[] = [
  {
    heading: "What you hand over",
    body: (
      <>
        <p>
          The bench takes one artifact at a time: pasted copy, a single frame, a recording, or a
          piece of footage. Nothing else is asked for. There is no account, no sign-in, and no field
          anywhere on this site that asks for your name, your address, or your organisation.
        </p>
      </>
    ),
  },
  {
    heading: "Where it is read",
    body: (
      <>
        <p>
          As the site stands, the artifact is read in your browser and is not uploaded. A file you
          choose is held in the page&rsquo;s own memory for as long as the tab is open; a frame is
          previewed through an object URL your browser creates locally. Closing or reloading the tab
          discards it. Nothing is written to a server, because there is no server-side examination
          yet.
        </p>
      </>
    ),
  },
  {
    heading: "What the desks report",
    body: (
      <>
        <p>
          The findings, figures and determinations printed on a desk record are fixtures — they are
          held in the shape the real record will take, and they are derived from the artifact&rsquo;s
          own properties, such as a file&rsquo;s name and size or the length of the copy you pasted,
          so that the same submission always produces the same record. They are not an assessment of
          your artifact, and they must not be read as one.
        </p>
      </>
    ),
  },
  {
    heading: "What is stored",
    body: (
      <>
        <p>
          Nothing you submit is stored. There is no database behind this site, no analytics script on
          any page, and no third-party tag collecting what you read or submit. The one network
          request the pages make is for the typefaces, which Next.js serves from this site&rsquo;s
          own domain rather than from a font provider.
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
          are fixtures written by us, not examinations of anybody&rsquo;s submitted material. Nothing
          you hand the bench is added to the index, and no examination you run appears anywhere
          another reader can see it.
        </p>
      </>
    ),
  },
  {
    heading: "When this changes",
    body: (
      <>
        <p>
          The moment a real examination model is attached, an artifact will have to leave your
          browser to be read, and that changes every clause above. When it does, this page will say
          exactly where the artifact goes, who processes it, how long it is held, and how to have it
          removed — before the first artifact is sent, not after.
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
      standfirst="Almost nothing, at present — because nothing you submit leaves your browser yet. Here is the whole of it, plainly."
      clauses={CLAUSES}
      foot={
        <>
          This note describes the site as it is built today, not as it is intended to work. It is
          written from the code rather than from a template, and it is short because the site does
          little: there is no account system, no analytics, and no examination model attached. If a
          clause here ever disagrees with what the site does, the site is wrong and the clause
          stands until it is fixed.
        </>
      }
    />
  );
}
