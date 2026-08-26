"use client";

import { createContext, useContext, useEffect, useSyncExternalStore } from "react";
import { ApiError, setAuthToken } from "@/lib/api/client";
import {
  login as loginRequest,
  readCurrentAccount,
  registerAccount,
  type AccountOut,
} from "@/lib/api/auth";

/**
 * The signed-in session.
 *
 * The session is not React state. It is an external thing React reads — a token in
 * `sessionStorage`, a slot in the API client, and a timer that fires when the token
 * dies — so it lives in a module-level store below and is published through
 * `useSyncExternalStore`. Modelling it as `useState` inside the provider meant every
 * change had to remember to also write storage and also push the token into the
 * client, in the right order, in a render React is allowed to discard. There is one
 * writer now, `commit`, and it does all three.
 *
 * Three further things are decisions rather than defaults.
 *
 * **The token lives in `sessionStorage`, not `localStorage`.** Either is readable by
 * script, so neither survives an XSS; what differs is the blast radius. There is no
 * refresh endpoint and an access token is good for half an hour, so persisting one
 * across browser sessions could not keep anybody signed in anyway — it would only
 * leave a credential on disk, shared across every tab, long after it stopped being
 * useful. Per-tab and gone when the tab closes costs a reader nothing here.
 *
 * **A restored session is trusted optimistically and then checked.** The stored
 * account is shown immediately so the masthead does not flicker through a signed-out
 * state on every navigation, and `GET /auth/me` runs behind it. A 401 clears the
 * session; an unreachable service does not, because "the backend is down" is not
 * evidence that a token is bad and signing the reader out would lose their session to
 * a restart of something else.
 *
 * **Signing out is local.** No endpoint revokes a token, so signing out forgets it and
 * the token itself stays valid at the server until it expires. The panel says so
 * rather than implying the session was destroyed.
 */

/** Namespaced so it cannot collide with anything else on the origin. */
const STORAGE_KEY = "veritas.session";

/**
 * Treat a token as dead this far before its stated expiry. A request that leaves at
 * `expiresAt - 1s` can easily arrive after it, and the clocks are not the same clock.
 */
const SKEW_MS = 30_000;

export type AuthStatus = "restoring" | "signed-out" | "signed-in";

interface StoredSession {
  token: string;
  /** Epoch milliseconds, computed once from `expires_in` at the time it was issued. */
  expiresAt: number;
  account: AccountOut;
}

interface Snapshot {
  status: AuthStatus;
  session: StoredSession | null;
}

// ================================================================ storage ====

function readStored(): StoredSession | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    if (
      typeof parsed.token !== "string" ||
      typeof parsed.expiresAt !== "number" ||
      !parsed.account
    ) {
      return null;
    }
    return parsed as StoredSession;
  } catch {
    // Storage can be unavailable outright — Safari in private mode throws on read —
    // and a hand-edited or half-written value is not worth distinguishing from that.
    return null;
  }
}

function writeStored(session: StoredSession | null): void {
  try {
    if (session === null) window.sessionStorage.removeItem(STORAGE_KEY);
    else window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // A session that cannot be stored still works for this page's lifetime.
  }
}

const live = (session: StoredSession): boolean =>
  session.expiresAt - SKEW_MS > Date.now();

// ================================================================== store ====

/**
 * Both terminal snapshots are constants so `getSnapshot` can return the same object
 * twice; a fresh literal each read is an infinite render loop.
 */
const RESTORING: Snapshot = { status: "restoring", session: null };
const SIGNED_OUT: Snapshot = { status: "signed-out", session: null };

/**
 * Module state, which on the server means state shared between requests — safe only
 * because nothing ever writes it there. Every writer below is an event handler or an
 * effect, neither of which runs during server rendering, and `serverSnapshot` hands
 * the renderer a constant.
 */
let snapshot: Snapshot = RESTORING;
let lapse: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const getSnapshot = (): Snapshot => snapshot;
const getServerSnapshot = (): Snapshot => RESTORING;

/**
 * The one writer. Publishes the snapshot, the stored copy and the API client's token
 * together, so there is no window in which a request could go out with the wrong
 * credential — or with none while the reader is signed in.
 */
function commit(next: Snapshot): void {
  snapshot = next;
  setAuthToken(next.session?.token ?? null);
  writeStored(next.session);

  /* Drop the session the moment the token stops being accepted, so a reader is never
     looking at a signed-in masthead over a dead token. Without this the first sign of
     expiry would be an unexplained 401 from whatever they clicked next. */
  if (lapse !== null) clearTimeout(lapse);
  lapse = null;
  if (next.session !== null) {
    const remaining = next.session.expiresAt - SKEW_MS - Date.now();
    lapse = setTimeout(forget, Math.max(remaining, 0));
  }

  for (const listener of listeners) listener();
}

function adopt(session: StoredSession): void {
  commit({ status: "signed-in", session });
}

function forget(): void {
  commit(SIGNED_OUT);
}

async function signIn(email: string, password: string): Promise<void> {
  const issued = await loginRequest({ email, password });
  adopt({
    token: issued.access_token,
    expiresAt: Date.now() + issued.expires_in * 1000,
    account: issued.user,
  });
}

async function openAccount(
  email: string,
  password: string,
  displayName: string,
): Promise<void> {
  await registerAccount({ email, password, display_name: displayName.trim() });
  await signIn(email, password);
}

/**
 * Read the stored session, publish it, then ask the service whether it is still good.
 *
 * Runs after hydration rather than during render: the server has no `sessionStorage`,
 * so a session read while rendering would make the first client render disagree with
 * the markup it is hydrating.
 */
function restore(signal: AbortSignal): void {
  const stored = readStored();

  if (stored === null || !live(stored)) {
    // `commit` rather than a bare snapshot swap: an expired token has to leave storage
    // and the client's token slot as well, not just the view.
    forget();
    return;
  }

  adopt(stored);

  readCurrentAccount({ signal })
    .then((account) => {
      // Re-adopt rather than merge: a display name changed elsewhere should land.
      adopt({ ...stored, account });
    })
    .catch((cause) => {
      if (cause instanceof ApiError && cause.status === 401) forget();
    });
}

// ================================================================ context ====

interface AuthValue {
  status: AuthStatus;
  /** The signed-in account, or null. */
  account: AccountOut | null;
  /**
   * Epoch milliseconds at which the token stops being accepted, or null when nobody
   * is signed in. Published so the panel can print when the session lapses: with no
   * refresh endpoint, that moment is a fact about the session and not an internal.
   */
  expiresAt: number | null;
  /**
   * Sign in. Raises `ApiError` on rejection so the form that called it renders the
   * message; a failed attempt is the form's state, not the session's.
   */
  signIn: (email: string, password: string) => Promise<void>;
  /** Open an account, then sign in with it. Raises the same way. */
  openAccount: (
    email: string,
    password: string,
    displayName: string,
  ) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

/**
 * Kicks the restore once and publishes the session to everything below it.
 *
 * The provider exists even though the store is a module: the restore must happen once
 * per application rather than once per reader of the session, and a component that
 * calls `useAuth` outside it should be told so rather than quietly seeing a session
 * nobody started.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { status, session } = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );

  useEffect(() => {
    const controller = new AbortController();
    restore(controller.signal);
    return () => controller.abort();
  }, []);

  /* Not memoised. Every function on it is a module function with a permanent
     identity, so the object changes exactly when the snapshot does — which is when a
     consumer needs to re-render anyway. */
  const value: AuthValue = {
    status,
    account: session?.account ?? null,
    expiresAt: session?.expiresAt ?? null,
    signIn,
    openAccount,
    signOut: forget,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth was called outside AuthProvider.");
  }
  return value;
}
