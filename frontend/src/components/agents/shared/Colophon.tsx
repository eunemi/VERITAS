import { Slug } from "./layout";
import { API_BASE_URL } from "@/lib/api/client";
import { DESK_ISSUE, type DeskDefinition } from "@/lib/desks";

/**
 * The colophon. Where the record was set, and — plainly — where the findings came
 * from and what leaves the browser to get them. This belongs at the foot of the
 * document, in the small type, not in a notice box in the middle of the page.
 *
 * A desk with no bench sends nothing anywhere, so it does not carry the sentence
 * about what submitting does.
 */
export function Colophon({ desk, open = true }: { desk: DeskDefinition; open?: boolean }) {
  return (
    <div className="border-t border-ink-black/15 pt-stack-md pb-stack-lg">
      <Slug className="text-ink-black/40">Colophon</Slug>
      <p className="font-body-sm mt-2.5 max-w-[86ch] text-[13px] leading-[21px] text-ink-black/50">
        Set at the Veritas intelligence desk · Agent {desk.number}, {desk.name} · File{" "}
        <span className="tabular">{desk.file}</span> · Issue{" "}
        <span className="tabular">{DESK_ISSUE}</span>.{" "}
        {open ? (
          <>
            The findings, figures and determination on this record are the examining
            service&rsquo;s own, returned by <span className="tabular">{API_BASE_URL}</span>.
            Submitting sends the artifact — the copy you paste, or the address you give — to that
            service, which reads it, searches the open web where the desk calls for it, and files
            what it finds. Nothing on a record is written by this page.
          </>
        ) : (
          <>
            This desk takes no submissions, so nothing on this page was sent anywhere and nothing
            on it is a finding. The desks that are open are examined by the service at{" "}
            <span className="tabular">{API_BASE_URL}</span>.
          </>
        )}
      </p>
    </div>
  );
}
