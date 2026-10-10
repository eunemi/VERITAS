"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ExamineOptions } from "@/lib/services/agentServices";
import type { VerificationOut } from "@/lib/api/client";
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
  const [progress, setProgress] = useState<VerificationOut | null>(null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  const open = useCallback(async (examine: (options: ExamineOptions) => Promise<T>) => {
    controller.current?.abort();
    const active = new AbortController();
    controller.current = active;
    setStatus("working");
    setRecord(null);
    setError(null);
    setProgress(null);
    try {
      const result = await examine({ signal: active.signal, onReading: (reading) => { if (!active.signal.aborted) setProgress(reading); } });
      if (active.signal.aborted) return;
      setRecord(result);
      setStatus("record");
    } catch (cause) {
      if (active.signal.aborted) return;
      setError(cause);
      setStatus("failed");
    }
  }, []);

  const reopen = useCallback(() => {
    controller.current?.abort();
    setRecord(null);
    setError(null);
    setStatus("bench");
    setProgress(null);
  }, []);

  return { status, record, error, open, reopen, progress, working: status === "working" };
}
