import type { Metadata } from "next";
import { MyFile } from "../MyFile";

export const metadata: Metadata = {
  title: "My file",
  description:
    "Every examination filed under your account, newest first. Private to the account that commissioned it.",
  robots: { index: false, follow: false },
};

/**
 * The reader's own half of the archive. Nothing on it can be rendered ahead of time —
 * the records belong to whoever is signed in — so the page is a shell around a client
 * component that reads the session and then the file.
 */
export default function ArchiveFilePage() {
  return <MyFile />;
}
