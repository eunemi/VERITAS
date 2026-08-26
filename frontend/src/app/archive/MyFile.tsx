"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHead, Slug, Spread } from "@/components/agents/shared/layout";
import { ArchiveTabs } from "@/components/archive/ArchiveTabs";
import { AccountTrigger } from "@/components/auth/AccountSlip";
import { NoticeBlock, noticeOf, type Notice } from "@/components/ui/Notice";
import { useAuth } from "@/context/AuthContext";
import {
  history,
  retrieve,
  type Examination,
  type FiledRecord,
} from "@/lib/services/agentServices";
import { DESK_ISSUE, DESKS } from "@/lib/desks";
import { clock, day } from "@/lib/stamp";
import { TONE_TEXT, toneOf } from "@/lib/types/agents";

/**
 * The reader's own file.
 *
 * `GET /verifications`, which is the one endpoint on this API that cannot be read
 * without a token: a record filed anonymously has no owner to match on, so there is no
 * signed-out version of this page to fall back to and it does not pretend otherwise.
 *
 * The list carries no desk reports — the history endpoint deliberately leaves them off,
 * since twenty records' worth of annotations and exhibits is a large response to print
 * twenty lines from. A row therefore fetches its own record when it is opened, and what
 * comes back is the same translation a fresh examination goes through.
 */

/** How many rows to ask for. The endpoint's own ceiling is 100. */
const PAGE = 50;

type Load =
  | { state: "reading" }
  | { state: "read"; rows: FiledRecord[] }
  | { state: "failed"; notice: Notice };

type Dossier =
  | { state: "reading" }
  | { state: "read"; examination: Examination }
  | { state: "failed"; notice: Notice };

/* ----------------------------------------------------------------- rows ---- */

/** The determination, or what the record is doing instead of carrying one. */
function Finding({ record }: { record: FiledRecord }) {
  if (record.verdict) {
    const tone = toneOf(record.verdict.determination);
    return (
      <>
        <Slug className={`block ${TONE_TEXT[tone]}`}>{record.verdict.determination}</Slug>
        <p className="font-body-sm text-body-sm mt-1.5 text-ink-black/70">
          Confidence{" "}
          <span className="tabular text-ink-black">{record.verdict.confidence}</span>
        </p>
      </>
    );
  }

  if (record.failure) {
    return (
      <>
        <Slug className="block text-secondary">No record</Slug>
        <p className="font-body-sm text-body-sm mt-1.5 text-ink-black/70">
          {record.failure.desk
            ? `Stopped at the ${record.failure.desk} desk.`
            : "The examination stopped before it was signed."}
        </p>
      </>
    );
  }

  return (
    <>
      <Slug className="block text-gold-ink">
        {record.status === "pending" ? "Not started" : "Still open"}
      </Slug>
      <p className="font-body-sm text-body-sm mt-1.5 text-ink-black/70">
        Nothing is signed yet.
      </p>
    </>
  );
}

/** The record itself, once a row has been opened and the desks' filings fetched. */
function RecordDossier({ examination }: { examination: Examination }) {
  const decision = examination.decision;

  return (
    <div className="border-t border-ink-black/15 bg-parchment px-5 py-stack-md">
      {decision ? (
        <>
          <Slug className={TONE_TEXT[toneOf(decision.verdict.determination)]}>
            {decision.verdict.determination} · {decision.verdict.confidence} confidence
          </Slug>
          <h4 className="font-headline-md mt-2 max-w-title text-[21px] leading-[1.3] font-semibold text-ink-black">
            {decision.verdict.headline}
          </h4>
          <p className="font-body-md text-read mt-stack-sm max-w-measure text-ink-black/70">
            {decision.verdict.rationale}
          </p>

          {decision.ledger.length > 0 ? (
            <dl className="mt-stack-md grid gap-x-gutter sm:grid-cols-2 lg:grid-cols-4">
              {decision.ledger.map((entry) => (
                <div key={entry.key} className="border-t border-ink-black/25 py-2.5">
                  <dt>
                    <Slug className="text-ink-black/70">{entry.key}</Slug>
                  </dt>
                  <dd className="font-body-md text-body-md tabular mt-1 text-ink-black">
                    {entry.value}
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
        </>
      ) : (
        <Slug className="text-ink-black/70">Nothing was signed on this record</Slug>
      )}

      {examination.filings.length > 0 ? (
        <div className="mt-stack-md">
          <Slug className="block border-t-2 border-ink-black pt-stack-sm text-ink-black">
            What each desk filed
          </Slug>
          <ul>
            {examination.filings.map((filing) => {
              const desk = DESKS[filing.desk];
              const verdict = filing.record.verdict;
              return (
                <li
                  key={filing.desk}
                  className="flex flex-wrap items-baseline justify-between gap-x-gutter gap-y-1 border-t border-ink-black/15 py-2.5"
                >
                  <span className="font-body-md text-body-md min-w-0 flex-1 text-ink-black">
                    <span className="font-semibold">{desk?.name ?? filing.desk}</span>{" "}
                    <span className="text-ink-black/70">{verdict.headline}</span>
                  </span>
                  <Slug className={`shrink-0 ${TONE_TEXT[toneOf(verdict.determination)]}`}>
                    {verdict.determination} · {verdict.confidence}
                  </Slug>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {examination.failure ? (
        <NoticeBlock
          className="mt-stack-md"
          heading={
            examination.failure.desk
              ? `Stopped at the ${examination.failure.desk} desk`
              : "The examination stopped"
          }
          notice={{
            detail: examination.failure.message,
            code: examination.failure.code,
          }}
        />
      ) : null}

      <p className="font-body-sm text-body-sm mt-stack-md max-w-measure text-ink-black/55">
        This is the signed record, not the marked-up artifact: the annotations each desk
        anchored to the copy, the plate or the transcript are printed at the desk that
        made them. Nothing on this page is derived — every figure is the one the desk
        filed.
      </p>
    </div>
  );
}

function FileRow({
  record,
  open,
  dossier,
  onToggle,
}: {
  record: FiledRecord;
  open: boolean;
  dossier: Dossier | undefined;
  onToggle: () => void;
}) {
  const panelId = `dossier-${record.id}`;

  return (
    <li className="border-t border-ink-black/25">
      <div className="grid gap-stack-sm py-stack-md lg:grid-cols-12 lg:gap-gutter">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 lg:col-span-3 lg:flex-col lg:gap-y-2">
          <Slug className="text-ink-black">{record.handedOver}</Slug>
          <Slug className="tabular text-ink-black/70">{clock(record.filed)}</Slug>
          {/* The file number is the record's uuid, printed in full: it is the only
              handle on the record, and a shortened one would not fetch it. */}
          <span className="font-mono-label text-label break-all text-ink-black/45">
            {record.id}
          </span>
        </div>

        <div className="lg:col-span-6">
          <h3 className="font-headline-md text-[19px] leading-[1.35] font-semibold break-words text-ink-black">
            {record.title}
          </h3>
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            aria-controls={panelId}
            className="mt-stack-sm cursor-pointer border-b border-ink-black/40 pb-0.5 transition-colors hover:border-secondary hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
          >
            <Slug className="text-ink-black/70">
              {open ? "Close the record" : "Open the record"}
            </Slug>
          </button>
        </div>

        <div className="lg:col-span-3">
          <Finding record={record} />
        </div>
      </div>

      {open ? (
        <div id={panelId} className="pb-stack-md">
          {dossier === undefined || dossier.state === "reading" ? (
            <p className="font-body-md text-body-md border-t border-ink-black/15 bg-parchment px-5 py-stack-md text-ink-black/55">
              Fetching the record…
            </p>
          ) : dossier.state === "failed" ? (
            <NoticeBlock heading="The record did not come back" notice={dossier.notice} />
          ) : (
            <RecordDossier examination={dossier.examination} />
          )}
        </div>
      ) : null}
    </li>
  );
}

/* ---------------------------------------------------------------- shell ---- */

/** The masthead, the tabs and the colophon, which every state of the page prints. */
function Shell({
  kicker,
  children,
  colophon,
}: {
  kicker: string;
  children: React.ReactNode;
  colophon: React.ReactNode;
}) {
  return (
    <main className="min-h-screen bg-background">
      <PageHeader
        section="The archive"
        standing="Your own file"
        kicker={kicker}
        title={["Everything you", "have filed."]}
        lede="A record filed while you are signed in belongs to your account: it is listed here, newest first, and it answers to nobody else."
      />

      <ArchiveTabs />

      <Spread className="pb-stack-xl">{children}</Spread>

      <Spread>
        <div className="border-t border-ink-black/25 pt-stack-sm pb-stack-lg">
          <Slug className="text-ink-black/70">Colophon</Slug>
          <p className="font-body-md text-body-md mt-2.5 max-w-measure text-ink-black/70">
            Set at the Veritas archive · Issue <span className="tabular">{DESK_ISSUE}</span>.{" "}
            {colophon}
          </p>
        </div>
      </Spread>
    </main>
  );
}

/* ------------------------------------------------------------------ file ---- */

/**
 * The file itself.
 *
 * Mounted under the account's own key, so signing out and back in as somebody else
 * gets a fresh component rather than a component that has to remember to throw away
 * the previous reader's rows. That is why the fetch runs once on mount and why nothing
 * here resets state when the session changes: identity does it.
 */
function Filed({ email }: { email: string }) {
  const [load, setLoad] = useState<Load>({ state: "reading" });
  const [open, setOpen] = useState<string | null>(null);
  const [dossiers, setDossiers] = useState<Record<string, Dossier | undefined>>({});

  useEffect(() => {
    const controller = new AbortController();

    history(PAGE, { signal: controller.signal })
      .then((rows) => setLoad({ state: "read", rows }))
      .catch((cause) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setLoad({ state: "failed", notice: noticeOf(cause) });
      });

    return () => controller.abort();
  }, []);

  const toggle = useCallback(
    (id: string) => {
      if (open === id) {
        setOpen(null);
        return;
      }
      setOpen(id);
      // A record already fetched is not fetched again: it is closed, and a closed
      // record does not change.
      if (dossiers[id]?.state === "read") return;

      setDossiers((held) => ({ ...held, [id]: { state: "reading" } }));
      retrieve(id)
        .then((examination) =>
          setDossiers((held) => ({ ...held, [id]: { state: "read", examination } })),
        )
        .catch((cause) =>
          setDossiers((held) => ({
            ...held,
            [id]: { state: "failed", notice: noticeOf(cause) },
          })),
        );
    },
    [open, dossiers],
  );

  const rows = load.state === "read" ? load.rows : [];

  /* Grouped by the day they were filed, in the order the endpoint returned them —
     newest first, and never re-sorted here. */
  const days: [string, FiledRecord[]][] = [];
  for (const record of rows) {
    const key = day(record.filed);
    const last = days[days.length - 1];
    if (last && last[0] === key) last[1].push(record);
    else days.push([key, [record]]);
  }

  const colophon = (
    <>
      Unlike the public index, nothing on this page is a fixture: every row is a record
      the desks actually signed for {email}, read from the examination service at the
      moment the page was opened. The most recent {PAGE} are listed
      {rows.length === PAGE
        ? ", and there may be older ones this list does not reach"
        : ""}
      . The session it was read under is held in this tab alone and lapses without being
      renewed.
    </>
  );

  return (
    <Shell
      kicker={
        load.state === "read"
          ? `${rows.length} record${rows.length === 1 ? "" : "s"} filed in your name`
          : "Private to your account"
      }
      colophon={colophon}
    >
      {load.state === "reading" ? (
        <p className="font-body-md text-body-md border-t-2 border-ink-black py-stack-lg text-ink-black/55">
          Reading your file…
        </p>
      ) : load.state === "failed" ? (
        <div className="border-t-2 border-ink-black pt-stack-md">
          <NoticeBlock heading="Your file did not come back" notice={load.notice} />
        </div>
      ) : rows.length === 0 ? (
        <div className="border-t-2 border-ink-black py-stack-lg">
          <Slug className="text-ink-black/70">Nothing filed yet</Slug>
          <p className="font-headline-md mt-stack-sm max-w-title text-[24px] leading-[1.25] font-semibold text-ink-black">
            Your file is open and empty.
          </p>
          <p className="font-body-md text-read mt-stack-sm max-w-measure text-ink-black/70">
            Anything you commission from here on is listed here. Records filed before you
            signed in are not — they were filed without an owner, and there is nothing to
            attach them to now.
          </p>
          <Link
            href="/investigate"
            className="font-mono-label text-mono-label mt-stack-md inline-block border border-ink-black bg-ink-black px-8 py-3.5 text-parchment transition-colors duration-300 hover:bg-transparent hover:text-ink-black focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black"
          >
            COMMISSION AN EXAMINATION
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-stack-lg">
          {days.map(([filedOn, group]) => (
            <section key={filedOn}>
              <SectionHead title={filedOn} note={`${group.length} filed`} />
              <ol className="mt-stack-sm">
                {group.map((record) => (
                  <FileRow
                    key={record.id}
                    record={record}
                    open={open === record.id}
                    dossier={dossiers[record.id]}
                    onToggle={() => toggle(record.id)}
                  />
                ))}
              </ol>
            </section>
          ))}
        </div>
      )}
    </Shell>
  );
}

/* ------------------------------------------------------------------ page ---- */

export function MyFile() {
  const { status, account } = useAuth();

  if (status === "signed-in" && account) {
    return <Filed key={account.id} email={account.email} />;
  }

  return (
    <Shell
      kicker="Private to your account"
      colophon="Nothing on this page is a fixture: it lists records the desks actually signed, and it can only be read by the account that commissioned them."
    >
      {status === "restoring" ? (
        <p className="font-body-md text-body-md border-t-2 border-ink-black py-stack-lg text-ink-black/55">
          Reading the session…
        </p>
      ) : (
        <div className="border-t-2 border-ink-black py-stack-lg">
          <Slug className="text-ink-black/70">Not signed in</Slug>
          <p className="font-headline-md mt-stack-sm max-w-title text-[24px] leading-[1.25] font-semibold text-ink-black">
            A file belongs to an account, and this browser is not signed in to one.
          </p>
          <p className="font-body-md text-read mt-stack-sm max-w-measure text-ink-black/70">
            There is no signed-out version of this page. A record filed without an account
            has no owner to list it under — its file number is the only handle on it, and
            it stays readable to anyone holding that number. Signing in first is what
            makes a record yours and private.
          </p>
          <div className="mt-stack-md flex flex-wrap items-center gap-stack-md">
            <AccountTrigger className="font-mono-label text-mono-label cursor-pointer border border-ink-black bg-ink-black px-8 py-3.5 text-parchment transition-colors duration-300 hover:bg-transparent hover:text-ink-black focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black" />
            <Link
              href="/archive"
              className="border-b border-ink-black/40 pb-1 transition-colors hover:border-secondary hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
            >
              <Slug className="text-ink-black/70">Read the public index instead</Slug>
            </Link>
          </div>
        </div>
      )}
    </Shell>
  );
}
