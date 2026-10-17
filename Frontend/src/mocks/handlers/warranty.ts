import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { OrderWire } from "@/features/orders/api/orders.schemas";
import {
  MAX_WARRANTY_MONTHS,
  type ComplaintLineWarranty,
  type OrderWarrantyWire,
  type WarrantyTermWire,
} from "@/features/warranty/api/warranty.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { calendarDayOf, shiftCalendarDay, todayInIndia } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockUuid } from "@/mocks/data/reference";
import { MOCK_WARRANTY_CATEGORIES, WARRANTY_SPACE } from "@/mocks/data/warranty";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * SO-009, CMPL-011, MSTR-017 · Warranty (FS-046, `docs/api/warranty.md`): a dispatch's period
 * starts on its DC date (else the dispatch day) for the months in force then for the product's
 * category, else the default's.
 */

function allowed(
  module: "masters" | "sales_orders" | "dispatch",
  action: "view" | "edit",
): boolean {
  return can(mockPermissionsFor(readMockRole()), module, action);
}

/** The term in force on a day for a category: its own, else the default. */
function monthsOn(categoryCode: string | null, day: string): number | null {
  const inForce = (term: WarrantyTermWire): boolean =>
    term.effective_from <= day && (term.effective_to === null || day < term.effective_to);
  const own = mockDb.warrantyTerms.find(
    (term) => term.product_category?.code === categoryCode && inForce(term),
  );
  const fallback = mockDb.warrantyTerms.find(
    (term) => term.product_category === null && inForce(term),
  );
  return (own ?? fallback)?.months ?? null;
}

/** The last covered day: the start plus the months, less a day. */
function endOf(start: string, months: number): string {
  const [year, month, day] = start.split("-").map(Number);
  const date = new Date(Date.UTC(year ?? 2026, (month ?? 1) - 1 + months, day ?? 1));
  return shiftCalendarDay(date.toISOString().slice(0, 10), -1);
}

type Status = "active" | "expired" | "none" | "unknown";

function periodFor(
  categoryCode: string | null,
  start: string,
  today: string,
): {
  end: string | null;
  months: number | null;
  status: Status;
} {
  const months = monthsOn(categoryCode, start);
  if (months === null) return { end: null, months: null, status: "unknown" };
  if (months === 0) return { end: null, months: 0, status: "none" };
  const end = endOf(start, months);
  return { end, months, status: today <= end ? "active" : "expired" };
}

function categoryOf(productId: string): string | null {
  return mockDb.products.find((product) => product.id === productId)?.product_category ?? null;
}

/** SO-009 · An order's warranty, as `GET /orders/{id}/warranty` answers. */
export function orderWarrantyFor(order: OrderWire): OrderWarrantyWire {
  const today = todayInIndia();
  const live = order.dispatches.filter((dispatch) => dispatch.voided_at === null);
  return {
    order_id: order.id,
    order_no: order.order_no,
    order_type: order.order_type,
    replacement_for: null,
    lines: order.lines.map((line) => {
      const category = categoryOf(line.product_id);
      const dispatches = live.flatMap((dispatch) => {
        const sent = dispatch.lines.find((item) => item.order_line_id === line.id);
        if (sent === undefined) return [];
        const start = dispatch.dc_date ?? calendarDayOf(dispatch.dispatched_at);
        return [
          {
            dispatch_id: dispatch.id,
            dispatch_no: dispatch.dispatch_no,
            qty: sent.qty,
            start,
            start_basis:
              dispatch.dc_date === null ? ("dispatched_at" as const) : ("dc_date" as const),
            ...periodFor(category, start, today),
          },
        ];
      });
      const latest = [...dispatches].sort((left, right) =>
        (right.end ?? "").localeCompare(left.end ?? ""),
      )[0];
      const claims = mockDb.complaints
        .filter(
          (complaint) => complaint.sales_order?.id === order.id && complaint.submitted_at !== null,
        )
        .flatMap((complaint) =>
          complaint.lines
            .filter((item) => item.product.id === line.product_id)
            .map((item) => {
              const raised = calendarDayOf(complaint.submitted_at ?? new Date().toISOString());
              const coverage =
                latest === undefined ? null : periodFor(category, latest.start, raised);
              return {
                complaint_id: complaint.id,
                complaint_no: complaint.complaint_no,
                status: complaint.status,
                raised_on: raised,
                defective_qty: item.defective_qty,
                warranty_status:
                  coverage === null
                    ? ("unknown" as const)
                    : coverage.status === "active"
                      ? ("in_warranty" as const)
                      : coverage.status,
              };
            }),
        );
      return {
        order_line_id: line.id,
        product: { id: line.product_id, description: line.description },
        qty_ordered: line.qty,
        qty_dispatched: line.qty_dispatched,
        dispatches,
        status: latest === undefined ? "not_dispatched" : latest.status,
        claims,
      };
    }),
  };
}

/**
 * CMPL-011 · A complaint line's warranty on the day the complaint was first submitted (today
 * for a draft): from the linked order's latest dispatch of the product, else the supply date.
 */
export function complaintLineWarranty(
  complaint: {
    sales_order: { id: string } | null;
    supply_date: string | null;
    submitted_at: string | null;
  },
  productId: string,
): ComplaintLineWarranty {
  const raised =
    complaint.submitted_at === null ? todayInIndia() : calendarDayOf(complaint.submitted_at);
  const category = categoryOf(productId);
  const order =
    complaint.sales_order === null
      ? undefined
      : mockDb.orders.find((item) => item.id === complaint.sales_order?.id);
  const starts = (order?.dispatches ?? [])
    .filter((dispatch) => dispatch.voided_at === null)
    .filter((dispatch) =>
      dispatch.lines.some(
        (sent) =>
          order?.lines.find((line) => line.id === sent.order_line_id)?.product_id === productId,
      ),
    )
    .map((dispatch) => dispatch.dc_date ?? calendarDayOf(dispatch.dispatched_at))
    .sort();
  const start = starts.at(-1) ?? complaint.supply_date;
  if (start === null || start === undefined) {
    return { status: "unknown", start: null, end: null, months: null, basis: null };
  }
  const period = periodFor(category, start, raised);
  return {
    status: period.status === "active" ? "in_warranty" : period.status,
    start,
    end: period.end,
    months: period.months,
    basis: starts.length > 0 ? "dispatch" : "supply_date",
  };
}

const termSchema = z.object({
  product_category_id: z.string().min(1).nullable(),
  months: z.number().int().min(0, "0 to 120.").max(MAX_WARRANTY_MONTHS, "0 to 120."),
  effective_from: z.iso.date("A date."),
});

export const warrantyHandlers = [
  http.get(buildApiUrl("/orders/:orderId/warranty"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("sales_orders", "view") || !allowed("dispatch", "view")) {
      return errorResponse(403, "forbidden", "Needs sales_orders.view and dispatch.view.");
    }
    const order = mockDb.orders.find((item) => item.id === params.orderId);
    if (order === undefined) return errorResponse(404, "not_found", "No such order.");
    return HttpResponse.json({ data: orderWarrantyFor(order) });
  }),

  http.get(buildApiUrl("/warranty-terms"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("masters", "view")) return errorResponse(403, "forbidden", "Needs masters.view.");
    return HttpResponse.json({ data: mockDb.warrantyTerms });
  }),

  http.post(buildApiUrl("/warranty-terms"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("masters", "edit")) return errorResponse(403, "forbidden", "Needs masters.edit.");
    const parsed = termSchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(422, "validation_failed", "Some fields need correcting.", {
        months: "0 to 120.",
      });
    }
    const body = parsed.data;
    if (body.effective_from <= todayInIndia()) {
      return errorResponse(422, "validation_failed", "From tomorrow or later.", {
        effective_from: "Tomorrow or later: a period never restates a recorded dispatch.",
      });
    }
    const category =
      body.product_category_id === null
        ? null
        : (MOCK_WARRANTY_CATEGORIES.find((item) => item.id === body.product_category_id) ??
          undefined);
    if (category === undefined) {
      return errorResponse(422, "validation_failed", "Unknown category.", {
        product_category_id: "Not a known category.",
      });
    }
    const sameCategory = (term: WarrantyTermWire): boolean =>
      (term.product_category?.id ?? null) === (category?.id ?? null);
    if (
      mockDb.warrantyTerms.some(
        (term) => sameCategory(term) && term.effective_from === body.effective_from,
      )
    ) {
      return errorResponse(409, "term_exists", "One already starts that day for that category.");
    }
    // The period in force ends the day the new one starts.
    for (const term of mockDb.warrantyTerms) {
      if (
        sameCategory(term) &&
        term.effective_to === null &&
        term.effective_from < body.effective_from
      ) {
        term.effective_to = body.effective_from;
      }
    }
    mockDb.warrantyTerms.push({
      id: mockUuid(WARRANTY_SPACE, 100 + mockDb.warrantyTerms.length),
      product_category: category,
      months: body.months,
      effective_from: body.effective_from,
      effective_to: null,
    });
    mockDb.warrantyTerms.sort(
      (left, right) =>
        Number(left.product_category !== null) - Number(right.product_category !== null) ||
        (left.product_category?.name ?? "").localeCompare(right.product_category?.name ?? "") ||
        right.effective_from.localeCompare(left.effective_from),
    );
    return HttpResponse.json({ data: mockDb.warrantyTerms }, { status: 201 });
  }),
];
