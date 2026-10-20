import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { OrderWire } from "@/features/orders/api/orders.schemas";
import {
  RATING_COMMENT_MAX,
  RATING_TARGETS,
  type DealerRatingWire,
  type RatingPageWire,
  type RatingSummaryRowWire,
  type RatingWire,
} from "@/features/ratings/api/ratings.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { PARTNER_ROLES } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { RATING_SPACE, ratingOnComplaint, ratingOnOrder } from "@/mocks/data/ratings";
import { mockUuid } from "@/mocks/data/reference";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { mockSettings } from "./settings";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

/**
 * RATE-001 … RATE-004 · Ratings for the mock backend (`api/services/ratings.py`, migration 051).
 * Staff read ratings through the order's or the complaint's view; a partner user reads its own
 * firm's, a customer's as the score only.
 */

const MAX_LIMIT = 100;
const DAY_MS = 86_400_000;
/** The statuses whose orders count towards the dealer rating. */
const PAYABLE = new Set(["approved", "partially_dispatched", "dispatched", "closed_short"]);

interface Caller {
  readonly staff: boolean;
  readonly partnerId: string | null;
  readonly may: (
    module: "sales_orders" | "complaints" | "payments",
    action: "view" | "edit",
  ) => boolean;
  readonly me: { readonly id: string; readonly full_name: string };
}

function caller(): Caller {
  const role = readMockRole();
  const me = mockMeFor(role).data;
  const permissions = mockPermissionsFor(role);
  return {
    staff: me.user_type === "staff",
    partnerId: me.partner?.id ?? null,
    may: (module, action) => can(permissions, module, action),
    me: { id: me.id, full_name: me.full_name },
  };
}

function visibleTo(who: Caller, rating: RatingWire): boolean {
  if (!who.staff) return who.partnerId !== null && rating.partner?.id === who.partnerId;
  return rating.complaint === null
    ? who.may("sales_orders", "view")
    : who.may("complaints", "view");
}

/** A dealer reads a customer's rating as the score only: no comment, no name. */
function asSeenBy(who: Caller, rating: RatingWire): RatingWire {
  return !who.staff && rating.rated_by === "customer"
    ? { ...rating, comment: null, entered_by: null }
    : rating;
}

function shippedOn(order: OrderWire, productId?: string): boolean {
  return order.lines.some(
    (line) =>
      (productId === undefined || line.product_id === productId) && Number(line.qty_dispatched) > 0,
  );
}

const createSchema = z.object({
  target: z.enum(RATING_TARGETS),
  sales_order_id: z.string().min(1).nullish(),
  complaint_id: z.string().min(1).nullish(),
  product_id: z.string().min(1).nullish(),
  score: z.number().int().min(1, "1 to 5 stars.").max(5, "1 to 5 stars."),
  comment: z.string().max(RATING_COMMENT_MAX, "Up to 1,000 characters.").nullish(),
});

function bandsOf(key: string, fallback: readonly number[]): readonly number[] {
  const value = mockSettings().find((setting) => setting.key === key)?.value;
  return Array.isArray(value) &&
    value.every((item) => typeof item === "number") &&
    value.length === 4
    ? value
    : fallback;
}

function windowDays(): number {
  const value = mockSettings().find(
    (setting) => setting.key === "dealer_rating_window_days",
  )?.value;
  return typeof value === "number" ? value : 365;
}

/** Days at or under the first band score 5, then 4, 3, 2; over the last, 1. */
function paymentScore(days: number, bands: readonly number[]): number {
  const index = bands.findIndex((band) => days <= band);
  return index === -1 ? 1 : 5 - index;
}

/** Rupees at or over the last band score 5, then 4, 3, 2; under the first, 1. */
function valueScore(value: number, bands: readonly number[]): number {
  let score = 1;
  bands.forEach((band, index) => {
    if (value >= band) score = index + 2;
  });
  return score;
}

/** RATE-004 · As `dealer_rating()`: worked out on every read from the orders and payments. */
function dealerRatingOf(partnerId: string): DealerRatingWire {
  const days = windowDays();
  const since = Date.now() - days * DAY_MS;
  const orders = mockDb.orders.filter(
    (order) =>
      order.partner?.id === partnerId &&
      (order.order_type === "commercial" || order.order_type === "industrial") &&
      PAYABLE.has(order.status) &&
      order.submitted_at !== null &&
      Date.parse(order.submitted_at) >= since,
  );
  let paidOrders = 0;
  let weightedDays = 0;
  let paidValue = 0;
  for (const order of orders) {
    const allocations = mockDb.payments
      .filter((payment) => payment.voided === null)
      .flatMap((payment) =>
        payment.allocations
          .filter((allocation) => allocation.sales_order.id === order.id)
          .map((allocation) => ({ on: payment.received_on, amount: Number(allocation.amount) })),
      )
      .sort((left, right) => left.on.localeCompare(right.on));
    const total = Number(order.totals.total);
    let paid = 0;
    const fullOn = allocations.find((allocation) => {
      paid += allocation.amount;
      return paid >= total - 0.5;
    })?.on;
    if (fullOn === undefined || order.submitted_at === null) continue;
    paidOrders += 1;
    const taken = Math.max(0, (Date.parse(fullOn) - Date.parse(order.submitted_at)) / DAY_MS);
    weightedDays += taken * total;
    paidValue += total;
  }
  const paymentDays = paidValue > 0 ? Math.round((weightedDays / paidValue) * 10) / 10 : null;
  const orderValue = orders.reduce((sum, order) => sum + Number(order.totals.taxable), 0);
  const pScore =
    paymentDays === null
      ? null
      : paymentScore(paymentDays, bandsOf("dealer_rating_payment_days", [7, 15, 30, 60]));
  const vScore =
    orders.length === 0
      ? null
      : valueScore(
          orderValue,
          bandsOf("dealer_rating_order_value", [100000, 500000, 1000000, 2500000]),
        );
  const feedback = mockDb.ratings.filter(
    (rating) => rating.partner?.id === partnerId && rating.rated_by === "customer",
  );
  return {
    partner_id: partnerId,
    on: todayInIndia(),
    window_days: days,
    orders: orders.length,
    paid_orders: paidOrders,
    payment_days: paymentDays === null ? null : paymentDays.toFixed(1),
    payment_score: pScore,
    order_value: orderValue.toFixed(2),
    value_score: vScore,
    rating: pScore === null || vScore === null ? null : ((pScore + vScore) / 2).toFixed(1),
    feedback: {
      count: feedback.length,
      average:
        feedback.length === 0
          ? null
          : (feedback.reduce((sum, rating) => sum + rating.score, 0) / feedback.length).toFixed(2),
    },
  };
}

export const ratingHandlers = [
  http.get(buildApiUrl("/ratings"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const who = caller();
    const url = new URL(request.url);
    const param = (name: string): string | null => url.searchParams.get(name) || null;
    const maxScore = param("max_score");
    const matches =
      scenario === "empty"
        ? []
        : mockDb.ratings
            .filter((rating) => visibleTo(who, rating))
            .filter((rating) => param("target") === null || rating.target === param("target"))
            .filter(
              (rating) =>
                param("partner_id") === null || rating.partner?.id === param("partner_id"),
            )
            .filter(
              (rating) =>
                param("product_id") === null || rating.product?.id === param("product_id"),
            )
            .filter((rating) => param("lead_id") === null || rating.lead?.id === param("lead_id"))
            .filter(
              (rating) =>
                param("sales_order_id") === null || rating.order?.id === param("sales_order_id"),
            )
            .filter(
              (rating) =>
                param("complaint_id") === null || rating.complaint?.id === param("complaint_id"),
            )
            .filter((rating) => maxScore === null || rating.score <= Number(maxScore));
    const limit = Math.min(MAX_LIMIT, Number(url.searchParams.get("limit") ?? 50) || 50);
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : (decodeCursor(cursor) ?? 0);
    const body: RatingPageWire = {
      data: matches.slice(offset, offset + limit).map((rating) => asSeenBy(who, rating)),
      meta: {
        limit,
        next_cursor: offset + limit < matches.length ? encodeCursor(offset + limit) : null,
      },
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/ratings/summary"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const who = caller();
    const groupBy = new URL(request.url).searchParams.get("group_by");
    if (groupBy !== "partner" && groupBy !== "product" && groupBy !== "target") {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        group_by: "partner, product or target.",
      });
    }
    const groups = new Map<string, { name: string; scores: number[] }>();
    const visible = scenario === "empty" ? [] : mockDb.ratings.filter((r) => visibleTo(who, r));
    for (const rating of visible) {
      const key =
        groupBy === "partner"
          ? rating.partner
          : groupBy === "product"
            ? rating.product === null
              ? null
              : { id: rating.product.id, name: rating.product.description }
            : { id: rating.target, name: rating.target };
      if (key === null) continue;
      const group = groups.get(key.id) ?? { name: key.name, scores: [] };
      group.scores.push(rating.score);
      groups.set(key.id, group);
    }
    const rows: RatingSummaryRowWire[] = [...groups.entries()]
      .map(([id, group]) => ({
        key: { id, name: group.name },
        count: group.scores.length,
        average: (
          group.scores.reduce((sum, score) => sum + score, 0) / group.scores.length
        ).toFixed(2),
        low: group.scores.filter((score) => score <= 2).length,
      }))
      .sort((left, right) => Number(left.average) - Number(right.average));
    return HttpResponse.json({ data: rows });
  }),

  http.post(buildApiUrl("/ratings"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const who = caller();
    const parsed = createSchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        Object.fromEntries(
          parsed.error.issues.map((issue) => [issue.path.map(String).join("."), issue.message]),
        ),
      );
    }
    const body = parsed.data;
    const ratedBy = who.staff ? "customer" : "dealer";
    let on: Pick<RatingWire, "partner" | "lead" | "order" | "complaint"> & {
      product: RatingWire["product"];
    };
    if (body.target === "service") {
      const complaint = mockDb.complaints.find((item) => item.id === body.complaint_id);
      if (complaint === undefined) return errorResponse(404, "not_found", "No such document.");
      if (who.staff && !who.may("complaints", "edit")) {
        return errorResponse(403, "forbidden", "Not permitted to rate this.");
      }
      if (!who.staff && complaint.partner?.id !== who.partnerId) {
        return errorResponse(
          403,
          "not_your_order",
          "A dealer rates its own orders and complaints.",
        );
      }
      if (complaint.status !== "closed") {
        return errorResponse(422, "not_rateable", "The complaint is not closed.");
      }
      on = { ...ratingOnComplaint(complaint), order: null, product: null };
    } else {
      const order = mockDb.orders.find((item) => item.id === body.sales_order_id);
      if (order === undefined) return errorResponse(404, "not_found", "No such document.");
      if (who.staff && !who.may("sales_orders", "edit")) {
        return errorResponse(403, "forbidden", "Not permitted to rate this.");
      }
      if (!who.staff && order.partner?.id !== who.partnerId) {
        return errorResponse(
          403,
          "not_your_order",
          "A dealer rates its own orders and complaints.",
        );
      }
      if (!shippedOn(order)) {
        return errorResponse(422, "not_rateable", "Nothing has shipped yet.");
      }
      let product: RatingWire["product"] = null;
      if (body.target === "product") {
        const line = order.lines.find((item) => item.product_id === body.product_id);
        if (body.product_id == null || line === undefined || !shippedOn(order, line.product_id)) {
          return errorResponse(
            422,
            "product_not_shipped",
            "That product has not shipped on this order.",
            { product_id: "not shipped" },
          );
        }
        product = { id: line.product_id, description: line.description };
      }
      on = { ...ratingOnOrder(order), complaint: null, product };
    }
    const exists = mockDb.ratings.some(
      (rating) =>
        rating.target === body.target &&
        rating.rated_by === ratedBy &&
        rating.order?.id === on.order?.id &&
        rating.complaint?.id === on.complaint?.id &&
        rating.product?.id === on.product?.id,
    );
    if (exists) return errorResponse(409, "rating_exists", "This has been rated already.");
    const rating: RatingWire = {
      id: mockUuid(RATING_SPACE, 1000 + mockDb.ratings.length),
      target: body.target,
      score: body.score,
      comment: body.comment?.trim() || null,
      rated_by: ratedBy,
      entered_by: who.me,
      entered_via: who.staff ? "staff" : "dealer",
      ...on,
      created_at: new Date().toISOString(),
    };
    mockDb.ratings.unshift(rating);
    return HttpResponse.json({ data: rating }, { status: 201 });
  }),

  http.get(buildApiUrl("/partners/:partnerId/dealer-rating"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const who = caller();
    const partnerId = String(params.partnerId);
    const known =
      mockDb.partners.some((partner) => partner.id === partnerId) ||
      mockDb.orders.some((order) => order.partner?.id === partnerId) ||
      PARTNER_ROLES.some((role) => mockMeFor(role).data.partner?.id === partnerId);
    if (!known) return errorResponse(404, "not_found", "No such partner.");
    const allowed = who.staff ? who.may("payments", "view") : who.partnerId === partnerId;
    if (!allowed) {
      return errorResponse(
        403,
        "rating_not_permitted",
        "The dealer rating is for staff who see payments.",
      );
    }
    return HttpResponse.json({ data: dealerRatingOf(partnerId) });
  }),
];
