"use client";

import Link from "next/link";
import { DeskFailure } from "@/components/agents/shared/DeskFailure";
import { DeskPage } from "@/components/agents/shared/DeskPage";
import { Slug } from "@/components/agents/shared/layout";
import { DESKS } from "@/lib/desks";
import { ExaminationError } from "@/lib/services/agentServices";

const desk = DESKS.video;

/**
 * The temporal desk has a page, a method and a place in the roster, but no examiner
 * behind it in the service: submitting footage returns `not_implemented`. So the page
 * says that instead of offering a bench that cannot produce a record.
 *
 * The failure is constructed here rather than provoked by a submission on purpose.
 * Sending a clip to prove it fails would cost the reader the wait and the service the
 * work to reach a conclusion already known.
 */
const NOT_BUILT = new ExaminationError(
  "not_implemented",
  "The temporal desk is not bound to an examiner in the examining service, so nothing is read from footage yet.",
  "video",
);

export default function VideoDesk() {
  return (
    <DeskPage
      desk={desk}
      status="failed"
      onReopen={() => {}}
      bench={null}
      failure={
        <DeskFailure error={NOT_BUILT}>
          <p className="font-body-md text-body-md max-w-measure text-ink-black/70">
            A clip&rsquo;s sound can be examined now. The speech desk transcribes a
            recording, pulls the claims out of what was said, and checks them — which
            covers most of what is asserted in footage, though not what is shown.
          </p>
          <Link
            href="/intel/audio"
            className="mt-stack-md inline-block border-b-2 border-secondary pb-1 transition-colors hover:border-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
          >
            <Slug className="text-secondary">Take it to the speech desk</Slug>
          </Link>
        </DeskFailure>
      }
    />
  );
}
