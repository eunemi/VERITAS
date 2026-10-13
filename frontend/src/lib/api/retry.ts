/**
 * Retry policy for reads that are safe to repeat. Submission retries are kept
 * separate because repeating a POST can open a second examination.
 */
export const MAX_READ_RETRIES = 3;
export const READ_RETRY_BASE_MS = 300;
export const READ_RETRY_MAX_MS = 2_000;
export const MAX_SUBMIT_RETRIES = 3;

export interface RetryableFailure {
  code?: string;
  status?: number;
}

export function isTransientReadFailure(error: RetryableFailure): boolean {
  return (
    error.code === "service_unreachable" ||
    error.status === 502 ||
    error.status === 503
  );
}

export function shouldRetryRead(error: RetryableFailure, retries: number): boolean {
  return retries < MAX_READ_RETRIES && isTransientReadFailure(error);
}

/** `retryNumber` is one-based. */
export function readRetryDelay(retryNumber: number): number {
  return Math.min(
    READ_RETRY_MAX_MS,
    READ_RETRY_BASE_MS * 2 ** Math.max(0, retryNumber - 1),
  );
}

export function shouldRetrySubmission(
  error: RetryableFailure,
  retries: number,
): boolean {
  return retries < MAX_SUBMIT_RETRIES && error.code === "service_busy";
}
