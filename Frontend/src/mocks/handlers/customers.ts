import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  CONSENT_CHANNELS,
  CUSTOMER_TYPES,
  type CustomerDetailWire,
  type CustomerPageWire,
  type CustomerWire,
} from "@/features/customers/api/customers.schemas";
import type { LeadWire, TimelineEventWire } from "@/features/leads/api/leads.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockUuid } from "@/mocks/data/reference";
import { mockMeFor } from "@/mocks/data/sessions";
import { findMockTerritory, mockTerritoryLineage } from "@/mocks/data/territories";
import { newestFirst } from "@/mocks/data/timeline";
import { mockDb } from "@/mocks/db";

import { leadEventsOf } from "./lead-events";
import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

/**
 * LEAD-016 … LEAD-018 · Customers (`docs/api/customers.md`). A customer shows when the user can
 * see one of its leads: staff all, a partner user those its dealer holds. Staff with leads edit
 * correct it; a dealer gets 403.
 */

const MAX_LIMIT = 100;

function mayView(): boolean {
  return can(mockPermissionsFor(readMockRole()), "leads", "view");
}

/** The leads of a customer this user can see, not deleted or merged, newest first. */
function visibleLeads(customer: CustomerWire): LeadWire[] {
  const role = readMockRole();
  const partnerId = isPartnerRole(role) ? (mockMeFor(role).data.partner?.id ?? null) : null;
  return mockDb.leads
    .filter((lead) => lead.customer_id === customer.id && lead.stage !== "merged")
    .filter((lead) => partnerId === null || lead.assigned_partner?.id === partnerId)
    .sort((left, right) => right.created_at.localeCompare(left.created_at));
}

function withCount(customer: CustomerWire): CustomerWire {
  return { ...customer, lead_count: visibleLeads(customer).length };
}

function detailOf(customer: CustomerWire): CustomerDetailWire {
  const leads = visibleLeads(customer);
  const ids = new Set(leads.map((lead) => lead.id));
  return {
    ...withCount(customer),
    leads: leads.slice(0, 100).map((lead) => ({
      id: lead.id,
      inquiry_no: lead.inquiry_no,
      stage: lead.stage,
      source: lead.source,
      campaign_name: lead.campaign_name ?? null,
      created_at: lead.created_at,
    })),
    quotations: mockDb.quotations
      .filter((quotation) => quotation.lead !== null && ids.has(quotation.lead.id))
      .slice(0, 100)
      .map((quotation) => ({
        id: quotation.id,
        quote_no: quotation.quote_no,
        status: quotation.status,
        total: quotation.totals.total,
        lead_id: quotation.lead?.id ?? "",
        sent_at: quotation.sent_at,
      })),
    orders: mockDb.orders
      .filter((order) => order.lead !== null && ids.has(order.lead.id))
      .slice(0, 100)
      .map((order) => ({
        id: order.id,
        order_no: order.order_no,
        status: order.status,
        total: order.totals.total,
        lead_id: order.lead?.id ?? "",
        submitted_at: order.submitted_at,
      })),
  };
}

function findVisible(customerId: unknown): CustomerWire | Response {
  if (!mayView()) return errorResponse(403, "forbidden", "Needs leads.view.");
  const customer = mockDb.customers.find((item) => item.id === customerId);
  if (customer === undefined || visibleLeads(customer).length === 0) {
    return errorResponse(404, "not_found", "No such customer, or none of its leads are yours.");
  }
  return customer;
}

const patchSchema = z.object({
  customer_type: z.enum(CUSTOMER_TYPES).nullish(),
  name: z.string().trim().min(1, "Enter the name.").max(200).nullish(),
  email: z.email("An email like name@example.com.").nullish(),
  territory_id: z.string().min(1).nullish(),
  village: z.string().trim().max(120).nullish(),
  address: z.string().trim().max(500).nullish(),
  survey_no: z.string().trim().max(60).nullish(),
  consent_given: z.boolean().nullish(),
  consent_channel: z.enum(CONSENT_CHANNELS).nullish(),
});

export const customerHandlers = [
  http.get(buildApiUrl("/customers"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (!mayView()) return errorResponse(403, "forbidden", "Needs leads.view.");
    const url = new URL(request.url);
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    if (q !== "" && q.length < 3) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        q: "At least 3 characters.",
      });
    }
    const territoryId = url.searchParams.get("territory_id");
    const digits = q.replace(/\D/g, "");
    const matches =
      scenario === "empty"
        ? []
        : mockDb.customers
            .filter((customer) => visibleLeads(customer).length > 0)
            .filter(
              (customer) =>
                q === "" ||
                customer.name.toLowerCase().includes(q) ||
                (digits.length >= 3 && customer.mobile.includes(digits)),
            )
            .filter(
              (customer) =>
                territoryId === null ||
                visibleLeads(customer).some((lead) =>
                  mockTerritoryLineage(lead.territory.id).some((step) => step.id === territoryId),
                ),
            )
            .sort((left, right) => right.created_at.localeCompare(left.created_at));
    const limit = Math.min(MAX_LIMIT, Number(url.searchParams.get("limit") ?? 50) || 50);
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : (decodeCursor(cursor) ?? 0);
    const body: CustomerPageWire = {
      data: matches.slice(offset, offset + limit).map(withCount),
      meta: {
        limit,
        next_cursor: offset + limit < matches.length ? encodeCursor(offset + limit) : null,
      },
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/customers/:customerId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const customer = findVisible(params.customerId);
    if (customer instanceof Response) return customer;
    return HttpResponse.json({ data: detailOf(customer) });
  }),

  http.get(buildApiUrl("/customers/:customerId/timeline"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const customer = findVisible(params.customerId);
    if (customer instanceof Response) return customer;
    const own: TimelineEventWire[] = mockDb.customerEvents.get(customer.id) ?? [
      {
        id: mockUuid(0xc058, mockDb.customers.indexOf(customer) + 1),
        kind: "customer.created",
        occurred_at: customer.created_at,
        actor: null,
        payload: {},
      },
    ];
    const events = [
      ...own.map((event) => ({ ...event, lead_id: null, inquiry_no: null })),
      ...visibleLeads(customer).flatMap((lead) =>
        leadEventsOf(lead).map((event) => ({
          ...event,
          lead_id: lead.id,
          inquiry_no: lead.inquiry_no,
        })),
      ),
    ].sort(newestFirst);
    const url = new URL(request.url);
    const limit = Math.min(MAX_LIMIT, Number(url.searchParams.get("limit") ?? 50) || 50);
    const before = url.searchParams.get("before");
    const offset = before === null ? 0 : (decodeCursor(before) ?? 0);
    return HttpResponse.json({
      data: events.slice(offset, offset + limit),
      meta: {
        limit,
        next_cursor: offset + limit < events.length ? encodeCursor(offset + limit) : null,
      },
    });
  }),

  http.patch(buildApiUrl("/customers/:customerId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const role = readMockRole();
    if (isPartnerRole(role) || !can(mockPermissionsFor(role), "leads", "edit")) {
      return errorResponse(403, "forbidden", "Staff with leads edit correct a customer.");
    }
    const customer = findVisible(params.customerId);
    if (customer instanceof Response) return customer;
    const parsed = patchSchema.safeParse(await request.json());
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
    if (body.consent_given === true && body.consent_channel == null) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        consent_channel: "Say how consent was given.",
      });
    }
    let territory = customer.territory;
    if (body.territory_id != null) {
      const found = findMockTerritory(body.territory_id);
      if (found === undefined || !["district", "taluka", "village"].includes(found.level)) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          territory_id: "An active district, taluka or village.",
        });
      }
      territory = { id: found.id, name: found.name, level: found.level };
    }
    const now = new Date().toISOString();
    const keepsConsent =
      body.consent_given === true &&
      customer.consent_given_at !== null &&
      customer.consent_channel === body.consent_channel;
    Object.assign(customer, {
      ...(body.customer_type == null ? {} : { customer_type: body.customer_type }),
      ...(body.name == null ? {} : { name: body.name }),
      ...(body.email === undefined ? {} : { email: body.email ?? null }),
      territory,
      ...(body.village === undefined ? {} : { village: body.village ?? null }),
      ...(body.address === undefined ? {} : { address: body.address ?? null }),
      ...(body.survey_no === undefined ? {} : { survey_no: body.survey_no ?? null }),
      ...(body.consent_given === true && !keepsConsent
        ? { consent_given_at: now, consent_channel: body.consent_channel ?? null }
        : {}),
      ...(body.consent_given === false ? { consent_given_at: null, consent_channel: null } : {}),
      updated_at: now,
    });
    const me = mockMeFor(role).data;
    const events = mockDb.customerEvents.get(customer.id) ?? [];
    mockDb.customerEvents.set(customer.id, [
      {
        id: mockUuid(0xc059, mockDb.customerEvents.size * 100 + events.length + 1),
        kind: "customer.updated",
        occurred_at: now,
        actor: { id: me.id, full_name: me.full_name },
        payload: body.consent_given == null ? {} : { consent_given: body.consent_given },
      },
      ...events,
    ]);
    return HttpResponse.json({ data: detailOf(customer) });
  }),
];
