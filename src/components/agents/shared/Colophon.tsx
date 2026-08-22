import { Slug } from "./layout";
import { DESK_ISSUE, type DeskDefinition } from "@/lib/desks";

/**
 * The colophon. Where the record was set, and — plainly — that the examination
 * model is not attached yet. This belongs at the foot of the document, in the
 * small type, not in a notice box in the middle of the page.
 */
export function Colophon({ desk }: { desk: DeskDefinition }) {
  return (
    <div className="border-t border-ink-black/15 pt-stack-md pb-stack-lg">
      <Slug className="text-ink-black/40">Colophon</Slug>
      <p className="font-body-sm mt-2.5 max-w-[86ch] text-[13px] leading-[21px] text-ink-black/50">
        Set at the Veritas intelligence desk · Agent {desk.number}, {desk.name} · File{" "}
        <span className="tabular">{desk.file}</span> · Issue{" "}
        <span className="tabular">{DESK_ISSUE}</span>. The examination model is not attached yet:
        the findings, figures and determination on this record are fixtures, held in the shape the
        real record will take. The artifact on the page is the one you submitted, and it is read in
        your browser only.
      </p>
    </div>
  );
}
