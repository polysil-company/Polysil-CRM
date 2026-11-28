"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useMemo } from "react";

import { subsidyCalculationQueryOptions } from "@/features/subsidy/api/subsidy.queries";
import type {
  CalculateRequest,
  SubsidyCalculation,
  SystemConfig,
} from "@/features/subsidy/api/subsidy.schemas";
import {
  planCalculation,
  type CalculationPlan,
  type CalculatorDraft,
  type DraftProblems,
} from "@/features/subsidy/lib/calculator-draft";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { readFieldErrors } from "@/lib/api/errors";

/** Calculate once typing pauses for this long. */
const CALCULATE_DEBOUNCE_MS = 450;

/** A request that never goes out: the query is off while there is nothing to calculate. */
const NOTHING: CalculateRequest = { system_type: "drip", crops: [] };

export interface SubsidyCalculationState {
  readonly plan: CalculationPlan;
  /**
   * The figures on screen. They stay, dimmed, while the next arrive, and go once the inputs
   * can't be calculated (SUBS-019).
   */
  readonly result: SubsidyCalculation | null;
  /** A newer set of inputs is waiting for its figures. */
  readonly calculating: boolean;
  /** The figures on screen belong to the inputs on screen. */
  readonly upToDate: boolean;
  /** Local mistakes (after a pause) and the backend's 422, by field path. */
  readonly problems: DraftProblems;
  /** The calculation failed for a reason no field explains. */
  readonly failed: boolean;
  readonly query: UseQueryResult<SubsidyCalculation>;
}

/**
 * SUBS-002 · Calculates the draft as it changes, after a pause. Nothing is stored, so there is
 * nothing to save: the screen prints the backend's figures and never computes its own.
 */
export function useSubsidyCalculation(
  draft: CalculatorDraft,
  system: SystemConfig,
  scheme: string | null = null,
): SubsidyCalculationState {
  const plan = useMemo(() => planCalculation(draft, system, scheme), [draft, system, scheme]);
  const debounced = useDebouncedValue(plan, CALCULATE_DEBOUNCE_MS);
  const query = useQuery({
    ...subsidyCalculationQueryOptions(debounced.request ?? NOTHING),
    enabled: debounced.request !== null,
  });

  const settled = debounced === plan;
  const upToDate =
    plan.request !== null &&
    settled &&
    query.data !== undefined &&
    !query.isPlaceholderData &&
    !query.isFetching;
  const serverProblems = query.isError && settled ? (readFieldErrors(query.error) ?? {}) : {};
  // SUBS-019 · Once typing pauses on inputs that can't be calculated (a mistake or a missing
  // field), the last figures go: they were for other inputs, and a farmer's subsidy read off
  // them is wrong (client report, 28 Nov). The backend refusing the inputs does the same.
  const cannotCalculate = settled && (debounced.request === null || query.isError);
  // Otherwise the last figures stay, dimmed, while the next arrive; another system's never show.
  const result =
    !cannotCalculate && query.data?.systemType === draft.systemType ? query.data : null;

  return {
    plan,
    result,
    calculating: plan.request !== null && !upToDate && !(query.isError && settled),
    upToDate,
    // Local checks wait for the same pause, so "1." on the way to "1.5" isn't called a mistake.
    problems: { ...serverProblems, ...debounced.problems },
    failed: query.isError && settled && Object.keys(serverProblems).length === 0,
    query,
  };
}
