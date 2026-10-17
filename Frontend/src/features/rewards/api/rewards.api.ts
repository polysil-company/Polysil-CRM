import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  balanceResponseSchema,
  giftListSchema,
  giftResponseSchema,
  ledgerPageSchema,
  ledgerRowResponseSchema,
  redemptionPageSchema,
  redemptionResponseSchema,
  ruleListSchema,
  ruleResponseSchema,
  settingsResponseSchema,
  type AdjustmentRequest,
  type Balance,
  type Gift,
  type GiftCreateRequest,
  type GiftPatchRequest,
  type HolderQuery,
  type LedgerPage,
  type LedgerRow,
  type Redemption,
  type RedemptionListParams,
  type RedemptionPage,
  type RewardRule,
  type RewardSettings,
  type RuleCreateRequest,
  type RulePatchRequest,
  type SettingsRequest,
} from "./rewards.schemas";

const log = createLogger({ file: "features/rewards/api/rewards.api.ts", dataId: "RWD-001" });

export interface WriteInput<TBody> {
  readonly body: TBody;
  readonly idempotencyKey: string;
}

function holderParams(holder: HolderQuery): Record<string, string | undefined> {
  if (holder.kind === "partner") return { partner_id: holder.id };
  if (holder.kind === "user") return { user_id: holder.id };
  return {};
}

/** RWD-001 · A balance: your own, or a partner's or user's in your scope. */
export function getBalance(holder: HolderQuery, signal?: AbortSignal): Promise<Balance> {
  return apiRequest({
    dataId: "RWD-001",
    logger: log,
    fn: "getBalance",
    path: "/rewards/balance",
    query: holderParams(holder),
    schema: balanceResponseSchema,
    signal,
  });
}

/** RWD-001 · Every change to that balance, newest first. */
export function getLedger(
  holder: HolderQuery,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<LedgerPage> {
  return apiRequest({
    dataId: "RWD-001",
    logger: log,
    fn: "getLedger",
    path: "/rewards/ledger",
    query: { ...holderParams(holder), cursor: cursor ?? undefined },
    schema: ledgerPageSchema,
    signal,
  });
}

/** RWD-001 · What a point is worth today and the most of an order points may pay. */
export function getRewardSettings(signal?: AbortSignal): Promise<RewardSettings> {
  return apiRequest({
    dataId: "RWD-001",
    logger: log,
    fn: "getRewardSettings",
    path: "/reward-settings",
    schema: settingsResponseSchema,
    signal,
  });
}

/** RWD-001 · The gift catalogue, cheapest first; `activeOnly` for what can be asked for. */
export function listGifts(activeOnly: boolean, signal?: AbortSignal): Promise<Gift[]> {
  return apiRequest({
    dataId: "RWD-001",
    logger: log,
    fn: "listGifts",
    path: "/gifts",
    query: { active: activeOnly ? "true" : undefined },
    schema: giftListSchema,
    signal,
  });
}

/** RWD-001, RWD-002 · Redemptions in your scope, newest first. */
export function listRedemptions(
  params: RedemptionListParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<RedemptionPage> {
  return apiRequest({
    dataId: "RWD-001",
    logger: log,
    fn: "listRedemptions",
    path: "/rewards/gift-redemptions",
    query: {
      status: params.status ?? undefined,
      kind: params.kind ?? undefined,
      cursor: params.cursor ?? undefined,
    },
    schema: redemptionPageSchema,
    signal,
  });
}

/** RWD-001 · Ask for a gift; the points are held at once. */
export function requestGift({
  body,
  idempotencyKey,
}: WriteInput<{ readonly gift_id: string }>): Promise<Redemption> {
  return apiRequest({
    dataId: "RWD-001",
    logger: log,
    fn: "requestGift",
    method: "POST",
    path: "/rewards/gift-redemptions",
    body,
    idempotencyKey,
    schema: redemptionResponseSchema,
  });
}

export type RedemptionDecision = "fulfil" | "reject" | "withdraw";

/**
 * RWD-001 withdraw (the requester), RWD-002 fulfil and reject (rewards.approve, not the
 * requester; a reject needs a remark). 409 redemption_closed once decided.
 */
export function decideRedemption(
  redemptionId: string,
  decision: RedemptionDecision,
  { body, idempotencyKey }: WriteInput<{ readonly remark: string | null }>,
): Promise<Redemption> {
  return apiRequest({
    dataId: decision === "withdraw" ? "RWD-001" : "RWD-002",
    logger: log,
    fn: "decideRedemption",
    method: "POST",
    path: `/rewards/gift-redemptions/${encodeURIComponent(redemptionId)}/${decision}`,
    body,
    idempotencyKey,
    schema: redemptionResponseSchema,
  });
}

/** RWD-003 · The earning rules, active first. */
export function listRules(signal?: AbortSignal): Promise<RewardRule[]> {
  return apiRequest({
    dataId: "RWD-003",
    logger: log,
    fn: "listRules",
    path: "/reward-rules",
    schema: ruleListSchema,
    signal,
  });
}

/** RWD-003 · Add an earning rule. 409 code_taken. */
export function createRule({
  body,
  idempotencyKey,
}: WriteInput<RuleCreateRequest>): Promise<RewardRule> {
  return apiRequest({
    dataId: "RWD-003",
    logger: log,
    fn: "createRule",
    method: "POST",
    path: "/reward-rules",
    body,
    idempotencyKey,
    schema: ruleResponseSchema,
  });
}

/** RWD-003 · Change a rule; a used one only its end date and active flag (409 rule_in_use). */
export function patchRule(
  ruleId: string,
  { body, idempotencyKey }: WriteInput<RulePatchRequest>,
): Promise<RewardRule> {
  return apiRequest({
    dataId: "RWD-003",
    logger: log,
    fn: "patchRule",
    method: "PATCH",
    path: `/reward-rules/${encodeURIComponent(ruleId)}`,
    body,
    idempotencyKey,
    schema: ruleResponseSchema,
  });
}

/** RWD-003 · Change the point value or the limit, from today; once a day. */
export function putRewardSettings({
  body,
  idempotencyKey,
}: WriteInput<SettingsRequest>): Promise<RewardSettings> {
  return apiRequest({
    dataId: "RWD-003",
    logger: log,
    fn: "putRewardSettings",
    method: "PUT",
    path: "/reward-settings",
    body,
    idempotencyKey,
    schema: settingsResponseSchema,
  });
}

/** RWD-003 · Add a gift. */
export function createGift({ body, idempotencyKey }: WriteInput<GiftCreateRequest>): Promise<Gift> {
  return apiRequest({
    dataId: "RWD-003",
    logger: log,
    fn: "createGift",
    method: "POST",
    path: "/gifts",
    body,
    idempotencyKey,
    schema: giftResponseSchema,
  });
}

/** RWD-003 · Change a gift; a pending request keeps the points it was asked at. */
export function patchGift(
  giftId: string,
  { body, idempotencyKey }: WriteInput<GiftPatchRequest>,
): Promise<Gift> {
  return apiRequest({
    dataId: "RWD-003",
    logger: log,
    fn: "patchGift",
    method: "PATCH",
    path: `/gifts/${encodeURIComponent(giftId)}`,
    body,
    idempotencyKey,
    schema: giftResponseSchema,
  });
}

/** RWD-003 · Add or take away points by hand, with a reason. */
export function adjustPoints({
  body,
  idempotencyKey,
}: WriteInput<AdjustmentRequest>): Promise<LedgerRow> {
  return apiRequest({
    dataId: "RWD-003",
    logger: log,
    fn: "adjustPoints",
    method: "POST",
    path: "/rewards/adjustments",
    body,
    idempotencyKey,
    schema: ledgerRowResponseSchema,
  });
}
