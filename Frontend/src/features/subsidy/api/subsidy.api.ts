import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  calculateResponseSchema,
  subsidyCategoriesSchema,
  subsidyConfigSchema,
  subsidyCropsSchema,
  type CalculateRequest,
  type SubsidyCalculation,
  type SubsidyCategory,
  type SubsidyConfig,
  type SubsidyCrop,
  type SystemType,
} from "./subsidy.schemas";

const log = createLogger({ file: "features/subsidy/api/subsidy.api.ts", dataId: "SUBS-002" });

/** SUBS-003 · GET /subsidy/config — what each system accepts, from the masters in force. */
export function getSubsidyConfig(signal?: AbortSignal): Promise<SubsidyConfig> {
  return apiRequest({
    dataId: "SUBS-003",
    logger: log,
    fn: "getSubsidyConfig",
    path: "/subsidy/config",
    schema: subsidyConfigSchema,
    signal,
  });
}

/** SUBS-003 · GET /subsidy/crops — the crop picker, each with its standard lateral spacing. */
export function listSubsidyCrops(signal?: AbortSignal): Promise<SubsidyCrop[]> {
  return apiRequest({
    dataId: "SUBS-003",
    logger: log,
    fn: "listSubsidyCrops",
    path: "/subsidy/crops",
    schema: subsidyCropsSchema,
    signal,
  });
}

/** SUBS-003 · GET /subsidy/categories — one system's categories, in the order they print. */
export function listSubsidyCategories(
  systemType: SystemType,
  signal?: AbortSignal,
): Promise<SubsidyCategory[]> {
  return apiRequest({
    dataId: "SUBS-003",
    logger: log,
    fn: "listSubsidyCategories",
    path: "/subsidy/categories",
    query: { system_type: systemType },
    schema: subsidyCategoriesSchema,
    signal,
  });
}

/**
 * SUBS-002 · POST /subsidy/calculate — a preview: nothing is stored and nothing changes, so it
 * takes no idempotency key and is safe to call as the designer types (debounced).
 */
export function calculateSubsidy(
  body: CalculateRequest,
  signal?: AbortSignal,
): Promise<SubsidyCalculation> {
  return apiRequest({
    dataId: "SUBS-002",
    logger: log,
    fn: "calculateSubsidy",
    method: "POST",
    path: "/subsidy/calculate",
    body,
    schema: calculateResponseSchema,
    signal,
  });
}
