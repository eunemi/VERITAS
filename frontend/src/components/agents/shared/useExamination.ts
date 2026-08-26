"use client";

import { useCallback, useState } from "react";
import type { DeskStatus } from "./SlugBar";

/**
 * The four states a desk can be in, and the one transition between them.
 *
 * Every desk does the same thing with a submission: mark itself open, wait, and end
 * up with either a record or a reason there isn't one. Holding that here keeps six
 * pages from each writing their own try/catch, and means a desk cannot end up
 * showing a stale record beside a fresh failure — the record and the error are
 * cleared together or not at all.
 */
export function useExamination<T>() {
  const [status, setStatus] = useState<DeskStatus>("bench");
  const [record, setRecord] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);

  const open = useCallback(async (examine: () => Promise<T>) => {
    setStatus("working");
    setRecord(null);
    setError(null);
    try {
      setRecord(await examine());
      setStatus("record");
    } catch (cause) {
      setError(cause);
      setStatus("failed");
    }
  }, []);

  const reopen = useCallback(() => {
    setRecord(null);
    setError(null);
    setStatus("bench");
  }, []);

  return { status, record, error, open, reopen, working: status === "working" };
}
