"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { Slug, Spread } from "@/components/agents/shared/layout";
import { Drawer, DrawerTrigger, type Dismiss } from "@/components/ui/Drawer";
import { NoticeBlock, noticeOf, type Notice } from "@/components/ui/Notice";
import { useAuth } from "@/context/AuthContext";
import { MIN_PASSWORD_LENGTH, MAX_EMAIL_LENGTH } from "@/lib/api/auth";
import { stamp } from "@/lib/stamp";

/**
 * The account panel.
 *
 * The same sheet of paper the commission slip is printed on, because it is the same
 * object: a drawer under the masthead's ink band. What is on it is a subscription
 * counter — sign in, or open an account — and, once signed in, the standing details
 * of the reader's own file.
 *
 * The panel does not close itself on a successful sign-in. It re-reads the session and
 * prints who the reader now is, which is the confirmation a form owes them; the alterna-
 * tive is a panel that vanishes and leaves them to infer it from the masthead.
 */

/* ---------------------------------------------------------------- field ---- */

/** One ruled line of the counter. Label above, rule under, in the desks' own type. */
function Field({
  label,
  note,
  type,
  value,
  onChange,
  autoComplete,
  maxLength,
  first = false,
}: {
  label: string;
  /** The rule, or what the field is for. Printed under the line, always visible. */
  note: string;
  type: "email" | "password" | "text";
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  maxLength: number;
  /** Marks the line the drawer opens on. */
  first?: boolean;
}) {
  const id = useId();
  return (
    <div className="border-t border-ink-black/15 px-5 py-4 first:border-t-0">
      <label htmlFor={id}>
        <Slug className="block text-ink-black/70">{label}</Slug>
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete={autoComplete}
        maxLength={maxLength}
        spellCheck={false}
        data-first={first ? "" : undefined}
        className="font-body-lg text-lede mt-2 w-full border-b border-ink-black/25 bg-transparent pb-1.5 text-ink-black focus:border-secondary focus:outline-none"
      />
      <p className="font-body-sm text-body-sm mt-2 text-ink-black/55">{note}</p>
    </div>
  );
}

/* ---------------------------------------------------------- the counter ---- */

type Mode = "sign-in" | "open";

function Counter() {
  const { signIn, openAccount } = useAuth();

  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [working, setWorking] = useState(false);
  const [failed, setFailed] = useState<Notice | null>(null);

  const opening = mode === "open";

  /* Only what the form can know on its own. The address is not pattern-matched here:
     the server normalises and validates addresses in one place, and a second rule in
     the browser is a way for the two to disagree over a real address. */
  const complete =
    email.trim() !== "" &&
    (opening ? password.length >= MIN_PASSWORD_LENGTH : password !== "");

  function change(next: Mode) {
    setMode(next);
    setFailed(null);
    setPassword("");
  }

  async function submit() {
    if (!complete || working) return;
    setWorking(true);
    setFailed(null);
    try {
      if (opening) await openAccount(email.trim(), password, displayName);
      else await signIn(email.trim(), password);
      // Nothing to reset on success: the provider flips the session and this whole
      // counter is replaced by the file below it.
    } catch (cause) {
      setFailed(noticeOf(cause));
      setPassword("");
    } finally {
      setWorking(false);
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-stack-md border-b-2 border-ink-black pb-stack-sm">
        <div>
          <Slug className="text-secondary">
            {opening ? "Open an account" : "Subscribers"}
          </Slug>
          <h2
            id="account-heading"
            className="font-masthead mt-stack-sm text-[clamp(34px,5.2vw,58px)] leading-[0.94] font-black tracking-[-0.02em] text-ink-black"
          >
            <span className="block">{opening ? "Start a" : "Sign in to"}</span>
            <span className="block pl-[0.06em] font-normal italic">
              {opening ? "file." : "your file."}
            </span>
          </h2>
        </div>
        <p className="font-body-sm text-body-sm max-w-[40ch] text-ink-black/60">
          A record filed while you are signed in is yours: it is private to your account
          and it appears in your file. Anything filed signed out belongs to nobody, and
          its file number is the only handle on it that exists.
        </p>
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
        className="mt-stack-lg grid gap-stack-lg lg:grid-cols-12 lg:gap-gutter"
      >
        <div className="lg:col-span-7">
          <div className="ticked bg-parchment">
            {opening ? (
              <Field
                label="Name, as it is printed"
                note="Optional. Left blank, the desks use the local part of your address."
                type="text"
                value={displayName}
                onChange={setDisplayName}
                autoComplete="name"
                maxLength={120}
                first
              />
            ) : null}

            <Field
              label="Address"
              note="Case is ignored. This is the only thing that identifies the account."
              type="email"
              value={email}
              onChange={setEmail}
              autoComplete="email"
              maxLength={MAX_EMAIL_LENGTH}
              first={!opening}
            />

            <Field
              label="Password"
              note={
                opening
                  ? `At least ${MIN_PASSWORD_LENGTH} characters. Length is the only rule — nothing here demands a symbol.`
                  : "Sent once, over the same connection as everything else on this page."
              }
              type="password"
              value={password}
              onChange={setPassword}
              autoComplete={opening ? "new-password" : "current-password"}
              maxLength={128}
            />
          </div>

          {failed ? (
            <NoticeBlock
              className="mt-stack-md"
              heading={opening ? "The account was not opened" : "Not signed in"}
              notice={failed}
            />
          ) : null}

          <div className="mt-stack-md flex flex-wrap items-center gap-stack-md">
            <button
              type="submit"
              disabled={!complete || working}
              className="font-mono-label text-mono-label cursor-pointer border border-ink-black bg-ink-black px-8 py-3.5 text-parchment transition-colors duration-300 hover:bg-transparent hover:text-ink-black focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:bg-ink-black disabled:hover:text-parchment"
            >
              {working
                ? opening
                  ? "OPENING…"
                  : "SIGNING IN…"
                : opening
                  ? "OPEN THE ACCOUNT"
                  : "SIGN IN"}
            </button>

            <button
              type="button"
              onClick={() => change(opening ? "sign-in" : "open")}
              className="cursor-pointer border-b border-ink-black/40 pb-1 transition-colors hover:border-secondary hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
            >
              <Slug className="text-ink-black/70">
                {opening ? "I already have an account" : "I have no account yet"}
              </Slug>
            </button>
          </div>
        </div>

        <aside className="lg:col-span-5">
          <Slug className="block border-t-2 border-ink-black pt-stack-sm text-ink-black">
            What an account changes
          </Slug>
          <dl className="mt-stack-sm">
            {[
              [
                "Your file",
                "Every record filed while you are signed in is listed in it, newest first.",
              ],
              [
                "Private by default",
                "An owned record answers only to its owner. To anyone else its file number is a number that does not exist.",
              ],
              [
                "Nothing is examined differently",
                "The desks read the artifact the same way signed in or out, and reach the same determination. An account only decides who can read the record afterwards.",
              ],
            ].map(([term, gloss]) => (
              <div key={term} className="border-t border-ink-black/15 py-3">
                <dt>
                  <Slug className="text-ink-black/70">{term}</Slug>
                </dt>
                <dd className="font-body-sm text-body-sm mt-1.5 text-ink-black/60">
                  {gloss}
                </dd>
              </div>
            ))}
          </dl>
        </aside>
      </form>
    </>
  );
}

/* -------------------------------------------------------------- my file ---- */

function Standing({ onLeave }: { onLeave: () => void }) {
  const { account, expiresAt, signOut } = useAuth();
  if (account === null) return null;

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-stack-md border-b-2 border-ink-black pb-stack-sm">
        <div>
          <Slug className="text-trust-green">Signed in</Slug>
          <h2
            id="account-heading"
            className="font-masthead mt-stack-sm text-[clamp(30px,4.4vw,48px)] leading-[1.02] font-black tracking-[-0.02em] text-ink-black"
          >
            {account.display_name}
          </h2>
        </div>
        <Link
          href="/archive/file"
          onClick={onLeave}
          className="font-mono-label text-mono-label border border-ink-black bg-ink-black px-8 py-3.5 text-parchment transition-colors duration-300 hover:bg-transparent hover:text-ink-black focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black"
        >
          OPEN MY FILE
        </Link>
      </div>

      <dl className="mt-stack-lg grid gap-x-gutter gap-y-0 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Address", account.email],
          ["Account opened", stamp(account.created_at)],
          ["Account number", account.id],
          ["This session lapses", expiresAt === null ? "—" : stamp(expiresAt)],
        ].map(([term, value]) => (
          <div key={term} className="border-t border-ink-black/25 py-stack-sm">
            <dt>
              <Slug className="text-ink-black/70">{term}</Slug>
            </dt>
            <dd className="font-body-md text-body-md mt-1.5 break-words text-ink-black">
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <div className="mt-stack-lg flex flex-wrap items-start justify-between gap-stack-md border-t-2 border-ink-black pt-stack-sm">
        <p className="font-body-sm text-body-sm max-w-measure text-ink-black/60">
          Signing out forgets the token held in this tab. It is not cancelled at the
          service — nothing there revokes one — so it simply stops being accepted at the
          time above. Your records stay in your file either way.
        </p>
        <button
          type="button"
          onClick={signOut}
          className="cursor-pointer border-b-2 border-secondary pb-1 transition-colors hover:border-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
        >
          <Slug className="text-secondary">Sign out</Slug>
        </button>
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- panel ---- */

/** What is printed on the drawer: the counter, or the reader's standing details. */
function AccountSlip({ close, leave }: Dismiss) {
  const { status } = useAuth();

  return (
    <Drawer onClose={close} labelledBy="account-heading" standing="Account">
      <Spread className="py-stack-lg">
        {status === "signed-in" ? <Standing onLeave={leave} /> : <Counter />}
      </Spread>
    </Drawer>
  );
}

/* --------------------------------------------------------------- action ---- */

/**
 * The masthead's account action.
 *
 * It prints the reader's own name once there is one, which is what tells them at a
 * glance that a record they file now will be theirs. While the session is being
 * restored it prints neither state: a flicker from "Sign in" to a name would say the
 * session was lost and then found.
 */
export function AccountTrigger({
  className,
  onOpen,
}: {
  className: string;
  onOpen?: () => void;
}) {
  const { status, account } = useAuth();

  const label =
    status === "restoring"
      ? "ACCOUNT"
      : account === null
        ? "SIGN IN"
        : account.display_name.toUpperCase();

  return (
    <DrawerTrigger className={className} onOpen={onOpen} panel={AccountSlip}>
      {label}
    </DrawerTrigger>
  );
}
