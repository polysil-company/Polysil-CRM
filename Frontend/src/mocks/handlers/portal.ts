import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { CustomerWire } from "@/features/customers/api/customers.schemas";
import {
  type PortalComplaintWire,
  type PortalEnquiryWire,
  type PortalMeWire,
  type PortalOrderWire,
  type PortalQuotationWire,
  type PortalRatingWire,
  PORTAL_RATING_TARGETS,
} from "@/features/portal/api/portal.schemas";
import type { RatingWire } from "@/features/ratings/api/ratings.schemas";
import type { MeResponse } from "@/features/session/api/session.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { readMockConsumerMobile } from "@/lib/dev/mock-settings";
import { RATING_SPACE, ratingOnComplaint, ratingOnOrder } from "@/mocks/data/ratings";
import { mockUuid } from "@/mocks/data/reference";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { mockSettings } from "./settings";
import { errorResponse } from "./shared";

/**
 * FARM-001 … FARM-003 · The farmers' portal for the mock backend (`api/routers/portal.py`).
 * A customer's number signs in by OTP as that farmer (see `auth.ts`). While signed in so,
 * every route outside `/auth` and `/portal` answers 403 `consumer_not_allowed`, and `/portal`
 * answers 403 `portal_off` while the setting is off. Staff and dealers get `not_a_consumer`.
 */

const MAX_ROWS = 100;

/** The signed-in farmer's customer record, or null when no farmer is signed in. */
function signedInCustomer(): CustomerWire | null {
  const mobile = readMockConsumerMobile();
  if (mobile === null) return null;
  return mockDb.customers.find((customer) => customer.mobile === mobile) ?? null;
}

/** `/auth/me` for a signed-in farmer, or null when the session is someone else's. */
export function mockConsumerMe(): MeResponse | null {
  const customer = signedInCustomer();
  if (customer === null) return null;
  return {
    data: {
      id: `cus-${customer.id}`,
      full_name: customer.name,
      user_type: "consumer",
      role: null,
      org_unit: null,
      partner: null,
      permissions: [],
      must_change_password: false,
    },
  };
}

function portalOn(): boolean {
  return mockSettings().find((setting) => setting.key === "consumer_portal")?.value === "on";
}

/** The farmer, or the refusal every portal route gives first. */
function guard(): CustomerWire | Response {
  const customer = signedInCustomer();
  if (customer === null) {
    return errorResponse(403, "not_a_consumer", "Staff and dealers use the main app.");
  }
  if (!portalOn()) return errorResponse(403, "portal_off", "The portal is switched off.");
  return customer;
}

function leadsOf(customer: CustomerWire): string[] {
  return mockDb.leads
    .filter((lead) => lead.customer_id === customer.id && lead.stage !== "merged")
    .map((lead) => lead.id);
}

function ordersOf(customer: CustomerWire): (typeof mockDb.orders)[number][] {
  const leads = new Set(leadsOf(customer));
  return mockDb.orders
    .filter((order) => order.lead !== null && leads.has(order.lead.id) && order.status !== "draft")
    .sort((left, right) => (right.submitted_at ?? "").localeCompare(left.submitted_at ?? ""))
    .slice(0, MAX_ROWS);
}

function complaintsOf(customer: CustomerWire): (typeof mockDb.complaints)[number][] {
  const leads = new Set(leadsOf(customer));
  return mockDb.complaints
    .filter(
      (complaint) =>
        complaint.status !== "draft" &&
        ((complaint.lead != null && leads.has(complaint.lead.id)) ||
          complaint.contact_mobile === customer.mobile),
    )
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .slice(0, MAX_ROWS);
}

function orderStatus(status: string): string {
  switch (status) {
    case "dispatched":
      return "dispatched";
    case "closed_short":
      return "closed";
    case "cancelled":
      return "cancelled";
    default:
      return "in_progress";
  }
}

function hasDispatch(order: (typeof mockDb.orders)[number]): boolean {
  return order.dispatches.some((dispatch) => dispatch.voided_at === null);
}

function myRatings(customer: CustomerWire): RatingWire[] {
  const orders = new Set(ordersOf(customer).map((order) => order.id));
  const complaints = new Set(complaintsOf(customer).map((complaint) => complaint.id));
  return mockDb.ratings.filter(
    (rating) =>
      rating.rated_by === "customer" &&
      (rating.target === "installation" || rating.target === "service") &&
      ((rating.order !== null && orders.has(rating.order.id)) ||
        (rating.complaint !== null && complaints.has(rating.complaint.id))),
  );
}

function asPortalRating(rating: RatingWire): PortalRatingWire {
  return {
    target: rating.target === "service" ? "service" : "installation",
    order_no: rating.order?.number ?? null,
    complaint_no: rating.complaint?.number ?? null,
    score: rating.score,
    comment: rating.entered_via === "portal" ? rating.comment : null,
    entered_via: rating.entered_via === "portal" ? "portal" : "staff",
    created_at: rating.created_at,
  };
}

function meOf(customer: CustomerWire): PortalMeWire {
  return {
    name: customer.name,
    mobile: customer.mobile,
    email: customer.email,
    village: customer.village,
    territory_name: customer.territory?.name ?? null,
    consent_given_at: customer.consent_given_at,
    consent_channel: customer.consent_channel,
  };
}

const ratingSchema = z.object({
  target: z.enum(PORTAL_RATING_TARGETS),
  order_no: z.string().min(1).nullish(),
  complaint_no: z.string().min(1).nullish(),
  score: z.number().int().min(1, "1 to 5 stars.").max(5, "1 to 5 stars."),
  comment: z.string().max(1000).nullish(),
});

/** Inside the portal only `/auth` and `/portal` answer; listed first so it runs first. */
export const consumerFenceHandlers = [
  http.all(buildApiUrl("/*"), ({ request }) => {
    if (readMockConsumerMobile() === null) return undefined;
    const path = new URL(request.url).pathname;
    if (/\/(auth|portal)(\/|$)/.test(path)) return undefined;
    return errorResponse(403, "consumer_not_allowed", "Farmers use the portal only.");
  }),
];

export const portalHandlers = [
  http.get(buildApiUrl("/portal/me"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const customer = guard();
    if (customer instanceof Response) return customer;
    return HttpResponse.json({ data: meOf(customer) });
  }),

  http.patch(buildApiUrl("/portal/me"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const customer = guard();
    if (customer instanceof Response) return customer;
    if (request.headers.get("idempotency-key") === null) {
      return errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.");
    }
    const parsed = z.object({ consent_given: z.boolean() }).safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        consent_given: "true or false.",
      });
    }
    const now = new Date().toISOString();
    if (parsed.data.consent_given) {
      const keeps = customer.consent_given_at !== null && customer.consent_channel === "portal";
      if (!keeps) {
        customer.consent_given_at = now;
        customer.consent_channel = "portal";
      }
    } else {
      customer.consent_given_at = null;
      customer.consent_channel = null;
    }
    customer.updated_at = now;
    return HttpResponse.json({ data: meOf(customer) });
  }),

  http.get(buildApiUrl("/portal/enquiries"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const customer = guard();
    if (customer instanceof Response) return customer;
    const data: PortalEnquiryWire[] =
      scenario === "empty"
        ? []
        : mockDb.leads
            .filter((lead) => lead.customer_id === customer.id && lead.stage !== "merged")
            .sort((left, right) => right.created_at.localeCompare(left.created_at))
            .slice(0, MAX_ROWS)
            .map((lead) => ({
              inquiry_no: lead.inquiry_no,
              status:
                lead.stage === "won" ? "won" : lead.stage === "lost" ? "closed" : "in_progress",
              system: lead.mis_system,
              created_at: lead.created_at,
            }));
    return HttpResponse.json({ data });
  }),

  http.get(buildApiUrl("/portal/quotations"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const customer = guard();
    if (customer instanceof Response) return customer;
    const leads = new Set(leadsOf(customer));
    const data: PortalQuotationWire[] =
      scenario === "empty"
        ? []
        : mockDb.quotations
            .filter(
              (quotation) =>
                quotation.lead !== null &&
                leads.has(quotation.lead.id) &&
                quotation.status !== "draft",
            )
            .sort((left, right) => (right.sent_at ?? "").localeCompare(left.sent_at ?? ""))
            .slice(0, MAX_ROWS)
            .map((quotation) => {
              const viaDealer = quotation.partner !== null;
              return {
                quote_no: quotation.quote_no,
                status:
                  quotation.status === "accepted"
                    ? "accepted"
                    : quotation.status === "rejected" || quotation.status === "expired"
                      ? "closed"
                      : "sent",
                total: viaDealer ? null : quotation.totals.total,
                sent_at: quotation.sent_at,
                valid_until: quotation.valid_until,
                link: viaDealer ? null : quotation.share_url,
              };
            });
    return HttpResponse.json({ data });
  }),

  http.get(buildApiUrl("/portal/orders"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const customer = guard();
    if (customer instanceof Response) return customer;
    const data: PortalOrderWire[] =
      scenario === "empty"
        ? []
        : ordersOf(customer).map((order) => ({
            order_no: order.order_no ?? "",
            status: orderStatus(order.status),
            total: order.partner === null ? order.totals.total : null,
            submitted_at: order.submitted_at,
            dispatches: order.dispatches
              .filter((dispatch) => dispatch.voided_at === null)
              .map((dispatch) => ({
                dc_no: dispatch.dc_no,
                dispatched_at: dispatch.dispatched_at,
              })),
          }));
    return HttpResponse.json({ data });
  }),

  http.get(buildApiUrl("/portal/complaints"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const customer = guard();
    if (customer instanceof Response) return customer;
    const data: PortalComplaintWire[] =
      scenario === "empty"
        ? []
        : complaintsOf(customer).map((complaint) => ({
            complaint_no: complaint.complaint_no ?? "",
            status:
              complaint.status === "closed" || complaint.status === "cancelled"
                ? "closed"
                : "in_progress",
            raised_at: complaint.submitted_at,
          }));
    return HttpResponse.json({ data });
  }),

  http.get(buildApiUrl("/portal/ratings"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const customer = guard();
    if (customer instanceof Response) return customer;
    return HttpResponse.json({ data: myRatings(customer).map(asPortalRating) });
  }),

  http.post(buildApiUrl("/portal/ratings"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const customer = guard();
    if (customer instanceof Response) return customer;
    if (request.headers.get("idempotency-key") === null) {
      return errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.");
    }
    const parsed = ratingSchema.safeParse(await request.json());
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
    let on: Pick<RatingWire, "partner" | "lead" | "order" | "complaint">;
    if (body.target === "installation") {
      const order = ordersOf(customer).find((item) => item.order_no === body.order_no);
      if (order === undefined) return errorResponse(404, "not_found", "No such order of yours.");
      if (!hasDispatch(order)) {
        return errorResponse(422, "not_rateable", "Nothing has shipped yet.");
      }
      on = { ...ratingOnOrder(order), complaint: null };
    } else {
      const complaint = complaintsOf(customer).find(
        (item) => item.complaint_no === body.complaint_no,
      );
      if (complaint === undefined) {
        return errorResponse(404, "not_found", "No such complaint of yours.");
      }
      if (complaint.status !== "closed") {
        return errorResponse(422, "not_rateable", "The complaint is not closed.");
      }
      on = { ...ratingOnComplaint(complaint), order: null };
    }
    const exists = mockDb.ratings.some(
      (rating) =>
        rating.rated_by === "customer" &&
        rating.target === body.target &&
        rating.product === null &&
        rating.order?.id === on.order?.id &&
        rating.complaint?.id === on.complaint?.id,
    );
    if (exists) {
      return errorResponse(409, "rating_exists", "Rated already, by you or by an officer for you.");
    }
    const rating: RatingWire = {
      id: mockUuid(RATING_SPACE, 2000 + mockDb.ratings.length),
      target: body.target,
      score: body.score,
      comment: body.comment?.trim() || null,
      rated_by: "customer",
      entered_by: null,
      entered_via: "portal",
      ...on,
      product: null,
      created_at: new Date().toISOString(),
    };
    mockDb.ratings.unshift(rating);
    return HttpResponse.json({ data: asPortalRating(rating) }, { status: 201 });
  }),
];
