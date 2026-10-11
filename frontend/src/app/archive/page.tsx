import type { Metadata } from "next";
import { ArchiveIndex } from "./ArchiveIndex";

export const metadata: Metadata = {
  title: "The archive",
  description:
    "Published example records, searchable by year, desk and determination, alongside the private file for signed-in submissions.",
};

/**
 * Search and the facets hold state, so the index itself is a client component and
 * this route stays a server component that can export metadata.
 */
export default function ArchivePage() {
  return <ArchiveIndex />;
}
