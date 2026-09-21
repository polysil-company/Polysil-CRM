"use client";

import { useEffect, useRef, useState } from "react";

import type { DataId } from "@/lib/data-ids";
import type { Logger } from "@/lib/logger";

export type AsyncActionState = "idle" | "loading" | "success" | "error";

export interface UseAsyncActionOptions<TArgs extends readonly unknown[], TResult> {
  /** The async work, e.g. `(input) => createLead.mutateAsync(input)`. */
  action: (...args: TArgs) => Promise<TResult>;
  logger: Logger;
  /** Handler name for logs, e.g. "handleCreateLead". */
  fn: string;
  dataId?: DataId;
  onSuccess?: (result: TResult) => void;
  onError?: (error: unknown) => void;
  /** How long "success" shows before returning to idle. */
  successMs?: number;
  /** How long "error" shows before returning to idle. */
  errorMs?: number;
  /** Minimum time "loading" stays visible, so fast responses don't flicker. */
  minLoadingMs?: number;
}

export interface AsyncAction<TArgs extends readonly unknown[], TResult> {
  readonly state: AsyncActionState;
  readonly error: unknown;
  readonly isBusy: boolean;
  /** Runs the action. Ignored while one is in flight (no double submits). Never throws. */
  run: (...args: TArgs) => Promise<TResult | undefined>;
  reset: () => void;
}

export const ASYNC_ACTION_TIMING = {
  successMs: 1500,
  errorMs: 2500,
  minLoadingMs: 400,
} as const;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/**
 * Drives a Button through loading → success | error → idle, logs the action
 * (File → Function → result) and prevents double submission.
 *
 *   const save = useAsyncAction({ action: submit, logger: log, fn: "handleSave", dataId: "LEAD-002" });
 *   <Button state={save.state} loadingLabel="Saving…" onClick={() => void save.run()}>Save</Button>
 */
export function useAsyncAction<TArgs extends readonly unknown[], TResult>(
  options: UseAsyncActionOptions<TArgs, TResult>,
): AsyncAction<TArgs, TResult> {
  const {
    action,
    logger,
    fn,
    dataId,
    onSuccess,
    onError,
    successMs = ASYNC_ACTION_TIMING.successMs,
    errorMs = ASYNC_ACTION_TIMING.errorMs,
    minLoadingMs = ASYNC_ACTION_TIMING.minLoadingMs,
  } = options;

  const [state, setState] = useState<AsyncActionState>("idle");
  const [error, setError] = useState<unknown>(undefined);
  const inFlight = useRef(false);
  const mounted = useRef(false);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearTimeout(idleTimer.current);
    };
  }, []);

  const returnToIdleAfter = (ms: number): void => {
    clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => {
      if (mounted.current) {
        setState("idle");
      }
    }, ms);
  };

  const run = async (...args: TArgs): Promise<TResult | undefined> => {
    if (inFlight.current) {
      return undefined;
    }
    inFlight.current = true;
    clearTimeout(idleTimer.current);
    setError(undefined);
    setState("loading");

    const startedAt = performance.now();
    const holdMinimum = (): Promise<void> =>
      sleep(Math.max(0, minLoadingMs - (performance.now() - startedAt)));

    try {
      const result = await logger.trace(
        fn,
        () => action(...args),
        dataId === undefined ? {} : { dataId },
      );
      await holdMinimum();
      if (mounted.current) {
        setState("success");
        returnToIdleAfter(successMs);
      }
      onSuccess?.(result);
      return result;
    } catch (caught) {
      await holdMinimum();
      if (mounted.current) {
        setError(caught);
        setState("error");
        returnToIdleAfter(errorMs);
      }
      onError?.(caught);
      return undefined;
    } finally {
      inFlight.current = false;
    }
  };

  const reset = (): void => {
    clearTimeout(idleTimer.current);
    setError(undefined);
    setState("idle");
  };

  return { state, error, isBusy: state === "loading", run, reset };
}
