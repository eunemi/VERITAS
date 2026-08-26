/**
 * Printed dates.
 *
 * The API sends timezone-aware UTC stamps and a reader is not in UTC, so both of
 * these convert. They are here rather than in a component because the account panel
 * and the reader's file print the same moments and a second formatter is a second
 * answer to what time a record was filed at.
 *
 * `Intl` is deliberate: month names and figure order belong to the reader's locale,
 * and the alternative is an English month table that is wrong for everybody else.
 */

/** `25 August 2026, 14:32` — the full moment, for a single record. */
export function stamp(at: string | number): string {
  const moment = new Date(at);
  if (Number.isNaN(moment.getTime())) return String(at);
  return moment.toLocaleString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** `25 August 2026` — the day, for the heading over a day's filings. */
export function day(at: string | number): string {
  const moment = new Date(at);
  if (Number.isNaN(moment.getTime())) return String(at);
  return moment.toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

/** `14:32` — the time alone, once the day is already printed above. */
export function clock(at: string | number): string {
  const moment = new Date(at);
  if (Number.isNaN(moment.getTime())) return "";
  return moment.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}
