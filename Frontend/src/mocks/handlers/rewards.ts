import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  REDEMPTION_STATUSES,
  RULE_BASES,
  RULE_HOLDERS,
  type GiftWire,
  type LedgerRowWire,
  type RedemptionWire,
  type RuleWire,
} from "@/features/rewards/api/rewards.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can, type ModuleCode } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockRewardId, STAFF_ME, type MockHolder } from "@/mocks/data/rewards";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * RWD-001 … RWD-003 · Reward points (FS-032, `docs/api/rewards.md`). Every action checks its
 * `rewards` permission as the router does; a field officer (V:own) reads only their own points.
 */

type Action = "view" | "create" | "edit" | "approve";

function allowed(action: Action, module: ModuleCode = "rewards"): boolean {
  return can(mockPermissionsFor(readMockRole()), module, action);
}

function forbidden(message = "The action is not in your permissions."): Response {
  return errorResponse(403, "forbidden", message);
}

function invalid(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

/** The caller's own holder: a partner user's partner, or the staff user. */
function myHolder(): MockHolder {
  const role = readMockRole();
  if (isPartnerRole(role)) {
    const partner = mockMeFor(role).data.partner;
    if (partner != null) return { type: "partner", id: partner.id, name: partner.name ?? "" };
  }
  return STAFF_ME;
}

/** A field officer's scope is own: no one else's points. */
function seesOthers(): boolean {
  const role = readMockRole();
  return !isPartnerRole(role) && role !== "employee";
}

function holderFrom(url: URL): MockHolder | Response {
  const partnerId = url.searchParams.get("partner_id");
  const userId = url.searchParams.get("user_id");
  if (partnerId !== null && partnerId !== "") {
    if (!seesOthers()) return errorResponse(404, "not_found", "Not found in your scope.");
    const partner = mockDb.partners.find((item) => item.id === partnerId);
    const known = mockDb.rewardLedger.find((entry) => entry.holder.id === partnerId)?.holder;
    if (partner === undefined && known === undefined) {
      return errorResponse(404, "not_found", "Not found in your scope.");
    }
    return { type: "partner", id: partnerId, name: partner?.name ?? known?.name ?? "" };
  }
  if (userId !== null && userId !== "" && userId !== "me" && userId !== STAFF_ME.id) {
    if (!seesOthers()) return errorResponse(404, "not_found", "Not found in your scope.");
    return errorResponse(404, "not_found", "Not found in your scope.");
  }
  return myHolder();
}

function balanceOf(holder: MockHolder): number {
  return mockDb.rewardLedger
    .filter((entry) => entry.holder.type === holder.type && entry.holder.id === holder.id)
    .reduce((sum, entry) => sum + entry.row.points, 0);
}

function currentSettings(): {
  point_value: string;
  max_redeem_pct: string;
  effective_from: string;
} {
  const today = todayInIndia();
  const [latest] = [...mockDb.rewardSettings]
    .filter((row) => row.effective_from <= today)
    .sort((left, right) => right.effective_from.localeCompare(left.effective_from));
  return latest ?? { point_value: "1.00", max_redeem_pct: "10.00", effective_from: today };
}

function addLedger(
  holder: MockHolder,
  points: number,
  kind: LedgerRowWire["kind"],
  reason: string,
): void {
  mockDb.rewardLedger.unshift({
    holder,
    row: {
      id: mockRewardId(5, mockDb.rewardLedger.length + 1),
      points,
      kind,
      reason,
      at: new Date().toISOString(),
      expires_at: null,
    },
  });
}

function fieldsOf(error: z.ZodError): Record<string, string> {
  return Object.fromEntries(
    error.issues.map((issue) => [issue.path.map(String).join("."), issue.message]),
  );
}

const ruleCreateSchema = z.object({
  code: z.string().trim().min(1, "Give it a code."),
  name: z.string().trim().min(1, "Name it."),
  holder: z.enum(RULE_HOLDERS),
  basis: z.enum(RULE_BASES),
  points: z.number().int().positive("At least 1 point."),
  per_amount: z.union([z.string(), z.number()]).nullish(),
  valid_from: z.iso.date({ message: "A date." }),
  valid_to: z.iso.date({ message: "A date." }).nullish(),
  expiry_days: z.number().int().positive("At least 1 day.").nullish(),
});

const rulePatchSchema = z.object({
  name: z.string().trim().min(1).optional(),
  points: z.number().int().positive().optional(),
  per_amount: z.union([z.string(), z.number()]).nullish(),
  valid_from: z.iso.date().optional(),
  valid_to: z.iso.date().nullish(),
  expiry_days: z.number().int().positive().nullish(),
  is_active: z.boolean().optional(),
});

const giftSchema = z.object({
  name: z.string().trim().min(1, "Name it."),
  description: z.string().nullish(),
  points_cost: z.number().int().positive("At least 1 point."),
});

function closed(redemption: RedemptionWire): Response {
  return errorResponse(409, "redemption_closed", `It is already ${redemption.status}.`, {
    status: redemption.status,
  });
}

async function remarkOf(request: Request): Promise<string | null> {
  const raw: unknown = await request.json().catch(() => ({}));
  const parsed = z.object({ remark: z.string().nullish() }).safeParse(raw);
  const remark = parsed.success ? (parsed.data.remark ?? "").trim() : "";
  return remark === "" ? null : remark;
}

function findRedemption(redemptionId: unknown): RedemptionWire | Response {
  const found = mockDb.rewardRedemptions.find((item) => item.id === redemptionId);
  return found ?? errorResponse(404, "not_found", "Not found in your scope.");
}

function holderOfRedemption(redemption: RedemptionWire): MockHolder {
  return {
    type: redemption.holder.type,
    id: redemption.holder.id,
    name: redemption.holder.name ?? "",
  };
}

export const rewardHandlers = [
  http.get(buildApiUrl("/rewards/balance"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const holder = holderFrom(new URL(request.url));
    if (holder instanceof Response) return holder;
    return HttpResponse.json({
      data: {
        holder: { type: holder.type, id: holder.id, name: holder.name },
        balance: balanceOf(holder),
        point_value: currentSettings().point_value,
      },
    });
  }),

  http.get(buildApiUrl("/rewards/ledger"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const holder = holderFrom(new URL(request.url));
    if (holder instanceof Response) return holder;
    const rows = mockDb.rewardLedger
      .filter((entry) => entry.holder.type === holder.type && entry.holder.id === holder.id)
      .map((entry) => entry.row);
    return HttpResponse.json({ data: rows, meta: { limit: 50, next_cursor: null } });
  }),

  http.post(buildApiUrl("/rewards/adjustments"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit") || isPartnerRole(readMockRole())) return forbidden();
    const parsed = z
      .object({
        partner_id: z.string().nullish(),
        user_id: z.string().nullish(),
        points: z.number().int(),
        reason: z.string(),
      })
      .safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const problems: Record<string, string> = {};
    if (body.points === 0) problems.points = "Not zero.";
    if (body.reason.trim() === "") problems.reason = "Say why.";
    if ((body.partner_id == null) === (body.user_id == null)) {
      problems.partner_id = "Name one partner or one user.";
    }
    if (Object.keys(problems).length > 0) return invalid(problems);
    // A seeded partner, or one already holding points (the demo dealer's partner).
    const partner =
      body.partner_id == null
        ? null
        : (mockDb.partners.find((item) => item.id === body.partner_id) ??
          mockDb.rewardLedger.find((entry) => entry.holder.id === body.partner_id)?.holder);
    if (partner === undefined) return invalid({ partner_id: "No such partner in your scope." });
    const holder: MockHolder =
      partner === null ? STAFF_ME : { type: "partner", id: partner.id, name: partner.name };
    addLedger(holder, body.points, "adjusted", body.reason.trim());
    return HttpResponse.json({ data: mockDb.rewardLedger[0]?.row }, { status: 201 });
  }),

  http.get(buildApiUrl("/reward-settings"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    return HttpResponse.json({ data: currentSettings() });
  }),

  http.put(buildApiUrl("/reward-settings"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit") || isPartnerRole(readMockRole())) return forbidden();
    const parsed = z
      .object({
        point_value: z.union([z.string(), z.number()]),
        max_redeem_pct: z.union([z.string(), z.number()]),
      })
      .safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const value = Number(parsed.data.point_value);
    const pct = Number(parsed.data.max_redeem_pct);
    const problems: Record<string, string> = {};
    if (!Number.isFinite(value) || value <= 0) problems.point_value = "More than 0.";
    if (!Number.isFinite(pct) || pct < 0 || pct > 100) problems.max_redeem_pct = "From 0 to 100.";
    if (Object.keys(problems).length > 0) return invalid(problems);
    const today = todayInIndia();
    if (mockDb.rewardSettings.some((row) => row.effective_from === today)) {
      return errorResponse(409, "settings_changed_today", "They were already changed today.");
    }
    const row = {
      point_value: value.toFixed(2),
      max_redeem_pct: pct.toFixed(2),
      effective_from: today,
    };
    mockDb.rewardSettings.push(row);
    return HttpResponse.json({ data: row });
  }),

  http.get(buildApiUrl("/gifts"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const activeOnly = new URL(request.url).searchParams.get("active") === "true";
    const gifts = mockDb.gifts
      .filter((gift) => !activeOnly || gift.is_active)
      .sort((left, right) => left.points_cost - right.points_cost);
    return HttpResponse.json({ data: gifts });
  }),

  http.post(buildApiUrl("/gifts"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit") || isPartnerRole(readMockRole())) return forbidden();
    const parsed = giftSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const gift: GiftWire = {
      id: mockRewardId(2, 100 + mockDb.gifts.length),
      name: parsed.data.name,
      description:
        parsed.data.description?.trim() === "" ? null : (parsed.data.description ?? null),
      points_cost: parsed.data.points_cost,
      is_active: true,
    };
    mockDb.gifts.push(gift);
    return HttpResponse.json({ data: gift }, { status: 201 });
  }),

  http.patch(buildApiUrl("/gifts/:giftId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit") || isPartnerRole(readMockRole())) return forbidden();
    const gift = mockDb.gifts.find((item) => item.id === params.giftId);
    if (gift === undefined) return errorResponse(404, "not_found", "Not found in your scope.");
    const parsed = giftSchema
      .partial()
      .extend({ is_active: z.boolean().optional() })
      .safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    if (body.name !== undefined) gift.name = body.name;
    if (body.description !== undefined) gift.description = body.description ?? null;
    if (body.points_cost !== undefined) gift.points_cost = body.points_cost;
    if (body.is_active !== undefined) gift.is_active = body.is_active;
    return HttpResponse.json({ data: gift });
  }),

  http.get(buildApiUrl("/reward-rules"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const rules = [...mockDb.rewardRules].sort(
      (left, right) => Number(right.is_active) - Number(left.is_active),
    );
    return HttpResponse.json({ data: rules });
  }),

  http.post(buildApiUrl("/reward-rules"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit") || isPartnerRole(readMockRole())) return forbidden();
    const parsed = ruleCreateSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const problems: Record<string, string> = {};
    if (body.basis === "lead_won" && body.holder !== "staff") {
      problems.holder = "A won lead earns for staff only.";
    }
    const perAmount = body.per_amount == null ? null : Number(body.per_amount);
    if (body.basis === "order_value" && (perAmount === null || !(perAmount > 0))) {
      problems.per_amount = "Points for every how many rupees.";
    }
    if (body.valid_to != null && body.valid_to < body.valid_from) {
      problems.valid_to = "On or after the start.";
    }
    if (Object.keys(problems).length > 0) return invalid(problems);
    if (mockDb.rewardRules.some((rule) => rule.code === body.code.toUpperCase())) {
      return errorResponse(409, "code_taken", "A rule with this code exists.", { code: "Taken." });
    }
    const rule: RuleWire = {
      id: mockRewardId(1, 100 + mockDb.rewardRules.length),
      code: body.code.toUpperCase(),
      name: body.name,
      holder: body.holder,
      basis: body.basis,
      points: body.points,
      per_amount: body.basis === "order_value" && perAmount !== null ? perAmount.toFixed(2) : null,
      valid_from: body.valid_from,
      valid_to: body.valid_to ?? null,
      expiry_days: body.expiry_days ?? null,
      is_active: true,
      used: false,
    };
    mockDb.rewardRules.unshift(rule);
    return HttpResponse.json({ data: rule }, { status: 201 });
  }),

  http.patch(buildApiUrl("/reward-rules/:ruleId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit") || isPartnerRole(readMockRole())) return forbidden();
    const rule = mockDb.rewardRules.find((item) => item.id === params.ruleId);
    if (rule === undefined) return errorResponse(404, "not_found", "Not found in your scope.");
    const parsed = rulePatchSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const changesTerms = (
      ["name", "points", "per_amount", "valid_from", "expiry_days"] as const
    ).some((key) => body[key] !== undefined);
    if (rule.used && changesTerms) {
      return errorResponse(
        409,
        "rule_in_use",
        "It has awarded points: only the end date and the active flag can change.",
      );
    }
    if (body.name !== undefined) rule.name = body.name;
    if (body.points !== undefined) rule.points = body.points;
    if (body.per_amount !== undefined) {
      rule.per_amount = body.per_amount === null ? null : Number(body.per_amount).toFixed(2);
    }
    if (body.valid_from !== undefined) rule.valid_from = body.valid_from;
    if (body.valid_to !== undefined) rule.valid_to = body.valid_to ?? null;
    if (body.expiry_days !== undefined) rule.expiry_days = body.expiry_days ?? null;
    if (body.is_active !== undefined) rule.is_active = body.is_active;
    return HttpResponse.json({ data: rule });
  }),

  http.get(buildApiUrl("/rewards/gift-redemptions"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const url = new URL(request.url);
    const status = url.searchParams.get("status");
    const kind = url.searchParams.get("kind");
    if (status !== null && !REDEMPTION_STATUSES.some((known) => known === status)) {
      return invalid({ status: REDEMPTION_STATUSES.join(", ") });
    }
    const mine = myHolder();
    const rows = mockDb.rewardRedemptions.filter(
      (row) =>
        (status === null || row.status === status) &&
        (kind === null || row.kind === kind) &&
        (seesOthers() || (row.holder.type === mine.type && row.holder.id === mine.id)),
    );
    return HttpResponse.json({ data: rows, meta: { limit: 50, next_cursor: null } });
  }),

  http.post(buildApiUrl("/rewards/gift-redemptions"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("create")) return forbidden();
    const parsed = z.object({ gift_id: z.string().min(1) }).safeParse(await request.json());
    if (!parsed.success) return invalid({ gift_id: "Choose a gift." });
    const gift = mockDb.gifts.find((item) => item.id === parsed.data.gift_id && item.is_active);
    if (gift === undefined) return invalid({ gift_id: "That gift isn't offered now." });
    const holder = myHolder();
    if (balanceOf(holder) < gift.points_cost) {
      return errorResponse(422, "insufficient_points", "Not enough points for that gift.");
    }
    addLedger(holder, -gift.points_cost, "redeemed", `Held for a gift: ${gift.name}`);
    const redemption: RedemptionWire = {
      id: mockRewardId(4, 100 + mockDb.rewardRedemptions.length),
      kind: "gift",
      holder: { type: holder.type, id: holder.id, name: holder.name },
      points: gift.points_cost,
      amount: null,
      status: "pending",
      gift: { ...gift },
      sales_order: null,
      remark: null,
      decided_at: null,
      created_at: new Date().toISOString(),
    };
    mockDb.rewardRedemptions.unshift(redemption);
    return HttpResponse.json({ data: redemption }, { status: 201 });
  }),

  http.post(buildApiUrl("/rewards/gift-redemptions/:rid/fulfil"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("approve") || isPartnerRole(readMockRole())) return forbidden();
    const redemption = findRedemption(params.rid);
    if (redemption instanceof Response) return redemption;
    if (redemption.status !== "pending") return closed(redemption);
    redemption.status = "fulfilled";
    redemption.remark = await remarkOf(request);
    redemption.decided_at = new Date().toISOString();
    return HttpResponse.json({ data: redemption });
  }),

  http.post(buildApiUrl("/rewards/gift-redemptions/:rid/reject"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("approve") || isPartnerRole(readMockRole())) return forbidden();
    const redemption = findRedemption(params.rid);
    if (redemption instanceof Response) return redemption;
    const remark = await remarkOf(request);
    if (remark === null) {
      return errorResponse(422, "remark_required", "Say why.", { remark: "Say why." });
    }
    if (redemption.status !== "pending") return closed(redemption);
    redemption.status = "rejected";
    redemption.remark = remark;
    redemption.decided_at = new Date().toISOString();
    addLedger(
      holderOfRedemption(redemption),
      redemption.points,
      "released",
      `Gift refused: ${redemption.gift?.name ?? "a gift"}`,
    );
    return HttpResponse.json({ data: redemption });
  }),

  http.post(buildApiUrl("/rewards/gift-redemptions/:rid/withdraw"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("create")) return forbidden();
    const redemption = findRedemption(params.rid);
    if (redemption instanceof Response) return redemption;
    const mine = myHolder();
    if (redemption.holder.type !== mine.type || redemption.holder.id !== mine.id) {
      return forbidden("Only the one who asked withdraws it.");
    }
    if (redemption.status !== "pending") return closed(redemption);
    redemption.status = "withdrawn";
    redemption.decided_at = new Date().toISOString();
    addLedger(
      mine,
      redemption.points,
      "released",
      `Gift withdrawn: ${redemption.gift?.name ?? "a gift"}`,
    );
    return HttpResponse.json({ data: redemption });
  }),
];
