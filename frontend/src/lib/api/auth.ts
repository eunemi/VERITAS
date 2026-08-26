/**
 * Transport for the account endpoints.
 *
 * Three calls, over the same `request` primitive and the same error envelope as the
 * examination endpoints. As with `./client`, the field names here are the wire's
 * snake_case and nothing is reshaped for a component — `@/context/AuthContext` owns
 * the session, and this module owns only what crosses the wire.
 *
 * Registration does not return a token. That is deliberate on the server's side:
 * `POST /auth/login` is the only endpoint that mints one, so it is the only one to
 * rate-limit and audit, and a client that wants to be signed in after signing up
 * pays one extra round trip for it.
 */

import { request, type CallOptions } from "./client";

/**
 * Mirrored from `app.security.passwords` so the form can say what the rule is before
 * a round trip. The server enforces it either way; this only saves a 422.
 */
export const MIN_PASSWORD_LENGTH = 8;
export const MAX_PASSWORD_LENGTH = 128;

/** Longest address RFC 5321 allows, matching the column and the request schema. */
export const MAX_EMAIL_LENGTH = 320;

/** An account, as the API publishes it. Four fields, and no password of any kind. */
export interface AccountOut {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
}

export interface TokenOut {
  access_token: string;
  token_type: "bearer";
  /** Seconds until the token stops being accepted. */
  expires_in: number;
  /** The signed-in account, so a client need not call `/auth/me` after signing in. */
  user: AccountOut;
}

/** `POST /auth/register` — creates the account and returns it, without a token. */
export async function registerAccount(
  body: { email: string; password: string; display_name?: string },
  options: CallOptions = {},
): Promise<AccountOut> {
  const { body: account } = await request<AccountOut>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
  });
  return account;
}

/**
 * `POST /auth/login` — exchange an email and password for a bearer token.
 *
 * Every rejection is the same 401 with the same message, whether the address is
 * unknown, the password is wrong, or the account has been closed. Nothing here should
 * try to tell those apart for the reader, because the server deliberately did not.
 */
export async function login(
  body: { email: string; password: string },
  options: CallOptions = {},
): Promise<TokenOut> {
  const { body: token } = await request<TokenOut>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
  });
  return token;
}

/**
 * `GET /auth/me` — the account the current token identifies.
 *
 * The server re-reads the account on every authenticated request, so a 200 here means
 * the session was live at the moment of this call rather than at the moment the token
 * was signed. That is what makes it worth calling on a restored session.
 */
export async function readCurrentAccount(
  options: CallOptions = {},
): Promise<AccountOut> {
  const { body } = await request<AccountOut>("/auth/me", {
    method: "GET",
    signal: options.signal,
  });
  return body;
}
