import type { Metadata } from "next";
import { ArchiveIndex } from "./ArchiveIndex";

export const metadata: Metadata = {
  title: "The archive",
  description:
    "Every examination Veritas has signed, searchable by year, desk and determination — including the ones the desks could not settle.",
};

/**
 * Search and the facets hold state, so the index itself is a client component and
 * this route stays a server component that can export metadata.
 */
export default function ArchivePage() {
  return <ArchiveIndex />;
}
