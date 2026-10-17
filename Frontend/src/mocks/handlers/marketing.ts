import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { MarketingOrderWire, MaterialWire } from "@/features/marketing/api/marketing.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import {
  lineFor,
  MARKETING_OFFICE,
  mockMarketingId,
  totalsOf,
  type MockMarketingOrder,
} from "@/mocks/data/marketing";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * MKT-002 … MKT-004 · Marketing material (FS-034, `docs/api/marketing-material.md`). Each call
 * checks `marketing_material` as the router does; `can` follows migration 038's rules.
 */

type Action = "view" | "create" | "edit" | "approve" | "delete";

function allowed(action: Action): boolean {
  return can(mockPermissionsFor(readMockRole()), "marketing_material", action);
}

function forbidden(code = "forbidden", message = "Not in your permissions."): Response {
  return errorResponse(403, code, message);
}

function invalid(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

function fieldsOf(error: z.ZodError): Record<string, string> {
  return Object.fromEntries(
    error.issues.map((issue) => [issue.path.map(String).join("."), issue.message]),
  );
}

function me(): { id: string; name: string; partner: { id: string; name: string } | null } {
  const data = mockMeFor(readMockRole()).data;
  const partner =
    data.partner == null ? null : { id: data.partner.id, name: data.partner.name ?? "" };
  return { id: data.id, name: data.full_name, partner };
}

function inScope(order: MockMarketingOrder): boolean {
  const { partner } = me();
  return partner === null || order.partner?.id === partner.id;
}

/** The buttons this caller may use now (migration 038's `marketing_order_act`). */
function canFor(order: MockMarketingOrder): MarketingOrderWire["can"] {
  const caller = me();
  const staff = caller.partner === null;
  const own = order.requested_by.id === caller.id;
  const deciding = order.status === "submitted" && staff && allowed("approve") && !own;
  return {
    approve: deciding,
    reject: deciding,
    cancel:
      (order.status === "submitted" && (own || allowed("delete"))) ||
      (order.status === "approved" && staff && allowed("edit")),
    dispatch: order.status === "approved" && staff && allowed("edit"),
  };
}

/** A dealer never sees who decided or dispatched. */
function wireFor(order: MockMarketingOrder): MarketingOrderWire {
  const partnerUser = me().partner !== null;
  return {
    ...order,
    decision:
      order.decision === null || !partnerUser ? order.decision : { ...order.decision, by: null },
    dispatch:
      order.dispatch === null || !partnerUser ? order.dispatch : { ...order.dispatch, by: null },
    can: canFor(order),
  };
}

function summaryOf(
  order: MockMarketingOrder,
): Omit<MockMarketingOrder, "lines" | "remark" | "decision" | "dispatch" | "cancel_remark"> {
  return {
    id: order.id,
    order_no: order.order_no,
    status: order.status,
    partner: order.partner,
    requested_by: order.requested_by,
    office: order.office,
    totals: order.totals,
    is_provisional: order.is_provisional,
    created_at: order.created_at,
  };
}

function filtered(url: URL): MockMarketingOrder[] {
  const statuses = url.searchParams.get("status")?.split(",").filter(Boolean) ?? [];
  const partnerId = url.searchParams.get("partner_id");
  const awaiting = url.searchParams.get("awaiting") === "me";
  const mine = url.searchParams.get("mine") === "true";
  const caller = me();
  return mockDb.marketingOrders
    .filter(inScope)
    .filter((order) => statuses.length === 0 || statuses.includes(order.status))
    .filter((order) => partnerId === null || order.partner?.id === partnerId)
    .filter((order) => !awaiting || canFor(order).approve)
    .filter((order) => !mine || order.requested_by.id === caller.id)
    .sort((left, right) => right.created_at.localeCompare(left.created_at));
}

const money = z
  .union([z.number(), z.string()])
  .transform(String)
  .pipe(z.string().regex(/^\d+(\.\d{1,2})?$/, "Rupees, like 120 or 120.50."));
const share = z
  .union([z.number(), z.string()])
  .transform(String)
  .pipe(
    z
      .string()
      .regex(/^\d+(\.\d{1,3})?$/, "A percentage, like 50.")
      .refine((value) => Number(value) <= 100, "At most 100."),
  );

const materialCreateSchema = z.object({
  code: z.string().trim().min(1, "Give it a code."),
  name: z.string().trim().min(1, "Name it."),
  description: z.string().nullish(),
  unit: z.string().trim().min(1).default("Nos"),
  price: money,
  company_share_pct: share.default("50"),
});

const materialPatchSchema = z.object({
  name: z.string().trim().min(1, "Name it.").optional(),
  description: z.string().nullish(),
  unit: z.string().trim().min(1).optional(),
  price: money.optional(),
  company_share_pct: share.optional(),
  is_active: z.boolean().optional(),
});

const orderCreateSchema = z.object({
  partner_id: z.string().nullish(),
  lines: z
    .array(
      z.object({ material_id: z.string().min(1), qty: z.number().int().min(1, "At least 1.") }),
    )
    .min(1, "Add at least one item."),
  remark: z.string().nullish(),
});

const remarkSchema = z.object({ remark: z.string().nullish() });

const dispatchSchema = z.object({
  dispatched_on: z.iso.date("A date."),
  reference: z.string().trim().min(1, "Say how it was sent, like a docket number."),
});

/** Materials whose price was changed today, once (the mock's stand-in for the price history). */
const changedToday = new Set<string>();

function findOrder(orderId: string): MockMarketingOrder | undefined {
  return mockDb.marketingOrders.find((order) => order.id === orderId && inScope(order));
}

export const marketingHandlers = [
  http.get(buildApiUrl("/marketing-materials"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const activeOnly =
      new URL(request.url).searchParams.get("active") === "true" || isPartnerRole(readMockRole());
    const rows = mockDb.materials.filter((item) => !activeOnly || item.is_active);
    return HttpResponse.json({ data: rows });
  }),

  http.post(buildApiUrl("/marketing-materials"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit") || me().partner !== null) return forbidden();
    const parsed = materialCreateSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const code = body.code.toUpperCase();
    if (mockDb.materials.some((item) => item.code.toUpperCase() === code)) {
      return errorResponse(409, "code_taken", "That code is taken.");
    }
    const material: MaterialWire = {
      id: mockMarketingId(1, 200 + mockDb.materials.length),
      code: body.code,
      name: body.name,
      description: body.description?.trim() === "" ? null : (body.description ?? null),
      unit: body.unit,
      price: Number(body.price).toFixed(2),
      company_share_pct: Number(body.company_share_pct).toFixed(2),
      image_url: null,
      is_active: true,
      is_provisional: false,
    };
    mockDb.materials.push(material);
    changedToday.add(material.id);
    return HttpResponse.json({ data: material }, { status: 201 });
  }),

  http.patch(buildApiUrl("/marketing-materials/:materialId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit") || me().partner !== null) return forbidden();
    const material = mockDb.materials.find((item) => item.id === params.materialId);
    if (material === undefined) return errorResponse(404, "not_found", "Not found in your scope.");
    const parsed = materialPatchSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const priceMoves =
      (body.price !== undefined && Number(body.price) !== Number(material.price)) ||
      (body.company_share_pct !== undefined &&
        Number(body.company_share_pct) !== Number(material.company_share_pct));
    if (priceMoves) {
      const used = mockDb.marketingOrders.some(
        (order) =>
          order.created_at.slice(0, 10) === todayInIndia() &&
          order.lines.some((line) => line.material.id === material.id),
      );
      if (changedToday.has(material.id) && used) {
        return errorResponse(
          409,
          "price_changed_today",
          "The price was already changed today and an order has used it. Try tomorrow.",
        );
      }
      if (body.price !== undefined) material.price = Number(body.price).toFixed(2);
      if (body.company_share_pct !== undefined) {
        material.company_share_pct = Number(body.company_share_pct).toFixed(2);
      }
      material.is_provisional = false;
      changedToday.add(material.id);
    }
    if (body.name !== undefined) material.name = body.name;
    if (body.description !== undefined) {
      material.description = body.description?.trim() === "" ? null : (body.description ?? null);
    }
    if (body.unit !== undefined) material.unit = body.unit;
    if (body.is_active !== undefined) material.is_active = body.is_active;
    return HttpResponse.json({ data: material });
  }),

  http.get(buildApiUrl("/marketing-orders"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const rows = filtered(new URL(request.url)).map(summaryOf);
    return HttpResponse.json({ data: rows, meta: { limit: 50, next_cursor: null } });
  }),

  http.get(buildApiUrl("/marketing-orders/export"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const lines = [
      ["Order", "Status", "Dealer", "Value", "Company share", "Dealer share"].join("\t"),
      ...filtered(new URL(request.url)).map((order) =>
        [
          order.order_no,
          order.status,
          order.partner?.name ?? "Office use",
          order.totals.value,
          order.totals.company_share,
          order.totals.dealer_share,
        ].join("\t"),
      ),
    ];
    return new HttpResponse(lines.join("\n"), {
      headers: {
        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "content-disposition": `attachment; filename="marketing-orders-${todayInIndia()}.xlsx"`,
      },
    });
  }),

  http.get(buildApiUrl("/marketing-orders/:orderId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const order = findOrder(String(params.orderId));
    if (order === undefined) return errorResponse(404, "not_found", "Not found in your scope.");
    return HttpResponse.json({ data: wireFor(order) });
  }),

  http.post(buildApiUrl("/marketing-orders"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("create")) return forbidden();
    const parsed = orderCreateSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const ids = body.lines.map((line) => line.material_id);
    const twice = ids.findIndex((value, index) => ids.indexOf(value) !== index);
    if (twice !== -1) return invalid({ [`lines.${String(twice)}.material_id`]: "Listed twice." });
    const caller = me();
    let partner: { id: string; name: string } | null = caller.partner;
    if (caller.partner === null && body.partner_id != null && body.partner_id !== "") {
      const found = mockDb.partners.find((item) => item.id === body.partner_id);
      if (found === undefined) return invalid({ partner_id: "Not a dealer in your scope." });
      partner = { id: found.id, name: found.name };
    }
    const index = mockDb.marketingOrders.length + 1;
    const lines: MockMarketingOrder["lines"] = [];
    for (const [position, line] of body.lines.entries()) {
      const material = mockDb.materials.find((item) => item.id === line.material_id);
      if (material === undefined || !material.is_active || material.price === null) {
        return errorResponse(422, "material_inactive", "An item is no longer offered.", {
          [`lines.${String(position)}.material_id`]: "No longer offered.",
        });
      }
      lines.push(lineFor(material, line.qty, position + 1, partner === null, index));
    }
    const order: MockMarketingOrder = {
      id: mockMarketingId(2, 100 + index),
      order_no: `MM/GJ/2026-27/${String(index).padStart(5, "0")}`,
      status: "submitted",
      partner,
      requested_by: { id: caller.id, name: caller.name },
      office: MARKETING_OFFICE,
      lines,
      totals: totalsOf(lines),
      remark: body.remark?.trim() === "" ? null : (body.remark ?? null),
      is_provisional: body.lines.some(
        (line) => mockDb.materials.find((item) => item.id === line.material_id)?.is_provisional,
      ),
      decision: null,
      dispatch: null,
      cancel_remark: null,
      created_at: new Date().toISOString(),
    };
    mockDb.marketingOrders.unshift(order);
    return HttpResponse.json({ data: wireFor(order) }, { status: 201 });
  }),

  ...(["approve", "reject", "cancel"] as const).map((action) =>
    http.post(buildApiUrl(`/marketing-orders/:orderId/${action}`), async ({ params, request }) => {
      const { failure } = await applyScenario();
      if (failure) return failure;
      if (!allowed("view")) return forbidden();
      const order = findOrder(String(params.orderId));
      if (order === undefined) return errorResponse(404, "not_found", "Not found in your scope.");
      const parsed = remarkSchema.safeParse(await request.json());
      if (!parsed.success) return invalid(fieldsOf(parsed.error));
      const remark =
        parsed.data.remark?.trim() === "" ? null : (parsed.data.remark?.trim() ?? null);
      const caller = me();
      const rights = canFor(order);
      if (action !== "cancel") {
        if (order.status !== "submitted") {
          return errorResponse(409, "status_changed", "Someone has already acted on it.");
        }
        if (order.requested_by.id === caller.id) {
          return forbidden("own_order", "Nobody approves their own order.");
        }
        if (!rights.approve) return forbidden("not_your_approval", "It isn't yours to decide.");
        if (action === "reject" && remark === null) {
          return errorResponse(422, "remark_required", "Say why.", { remark: "Say why." });
        }
        order.status = action === "approve" ? "approved" : "rejected";
        order.decision = {
          status: order.status,
          by: { id: caller.id, name: caller.name },
          at: new Date().toISOString(),
          remark,
        };
      } else {
        if (order.status !== "submitted" && order.status !== "approved") {
          return errorResponse(409, "status_changed", "It can no longer be cancelled.");
        }
        if (!rights.cancel) return forbidden();
        if (order.status === "approved" && remark === null) {
          return errorResponse(422, "remark_required", "Say why.", { remark: "Say why." });
        }
        order.status = "cancelled";
        order.cancel_remark = remark;
      }
      return HttpResponse.json({ data: wireFor(order) });
    }),
  ),

  http.post(buildApiUrl("/marketing-orders/:orderId/dispatch"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const order = findOrder(String(params.orderId));
    if (order === undefined) return errorResponse(404, "not_found", "Not found in your scope.");
    const parsed = dispatchSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    if (order.status !== "approved") {
      return errorResponse(409, "status_changed", "It isn't waiting to be sent.");
    }
    if (!canFor(order).dispatch) return forbidden();
    if (parsed.data.dispatched_on > todayInIndia()) {
      return invalid({ dispatched_on: "Not in the future." });
    }
    const caller = me();
    order.status = "dispatched";
    order.dispatch = {
      dispatched_on: parsed.data.dispatched_on,
      reference: parsed.data.reference,
      by: { id: caller.id, name: caller.name },
    };
    return HttpResponse.json({ data: wireFor(order) });
  }),
];
