import { z } from "zod";

import { timelineEventSchema } from "@/features/leads/api/leads.schemas";
import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";

/**
 * LEAD-016 … LEAD-018 · The customer record (FS-041, `customer-record.md`): a lead that reaches
 * qualified gets a customer, found by mobile or made new; later leads from that number join it.
 */

export const CUSTOMER_TYPES = ["farmer", "institution", "company"] as const;
export type CustomerType = (typeof CUSTOMER_TYPES)[number];

export const CONSENT_CHANNELS = ["whatsapp", "form", "verbal", "written"] as const;
export type ConsentChannel = (typeof CONSENT_CHANNELS)[number];

/** `q` needs at least this many characters (name or mobile). */
export const CUSTOMER_SEARCH_MIN_LENGTH = 3;
export const CUSTOMER_PAGE_SIZE = 50;

const id = z.string().min(1);
const isoDateTime = z.iso.datetime({ offset: true });

const customerWireSchema = z.object({
  id,
  /** farmer, institution or company; an unknown one reads as a farmer. */
  customer_type: z.string(),
  name: z.string(),
  /** E.164: the customer's identity, one customer per number. */
  mobile: z.string(),
  email: z.string().nullable(),
  territory: z.object({ id, name: z.string(), level: z.string() }).nullable(),
  village: z.string().nullable(),
  address: z.string().nullable(),
  survey_no: z.string().nullable(),
  /** Null: not given, or withdrawn. */
  consent_given_at: isoDateTime.nullable(),
  consent_channel: z.string().nullable(),
  /** Its leads you can see, not counting deleted or merged ones. */
  lead_count: z.number().int().nonnegative(),
  created_at: isoDateTime,
  updated_at: isoDateTime,
});

export type CustomerWire = z.input<typeof customerWireSchema>;

function typeOf(value: string): CustomerType {
  return CUSTOMER_TYPES.find((type) => type === value) ?? "farmer";
}

function channelOf(value: string | null): ConsentChannel | null {
  return CONSENT_CHANNELS.find((channel) => channel === value) ?? null;
}

function toCustomer(wire: z.output<typeof customerWireSchema>): Customer {
  return {
    id: wire.id,
    type: typeOf(wire.customer_type),
    name: wire.name.trim() || "Unnamed customer",
    mobile: wire.mobile,
    email: wire.email,
    territory: wire.territory,
    village: wire.village,
    address: wire.address,
    surveyNo: wire.survey_no,
    consentGivenAt: wire.consent_given_at,
    consentChannel: channelOf(wire.consent_channel),
    leadCount: wire.lead_count,
    createdAt: wire.created_at,
    updatedAt: wire.updated_at,
  };
}

export interface Customer {
  readonly id: string;
  readonly type: CustomerType;
  readonly name: string;
  readonly mobile: string;
  readonly email: string | null;
  readonly territory: { readonly id: string; readonly name: string; readonly level: string } | null;
  readonly village: string | null;
  readonly address: string | null;
  readonly surveyNo: string | null;
  readonly consentGivenAt: string | null;
  readonly consentChannel: ConsentChannel | null;
  readonly leadCount: number;
  readonly createdAt: string;
  readonly updatedAt: string;
}

export const customerSchema = customerWireSchema.transform(toCustomer);

/** GET /customers — newest first, one row at a time. */
export const customerPageSchema = cursorPageSchema(customerSchema);
export type CustomerPage = CursorPage<Customer>;
export type CustomerPageWire = { data: CustomerWire[]; meta: PageMetaWire };

const customerLeadWireSchema = z.object({
  id,
  inquiry_no: z.string(),
  stage: z.string(),
  /** The lead source code: what brought this enquiry. */
  source: z.string(),
  campaign_name: z.string().nullable(),
  created_at: isoDateTime,
});

const customerQuotationWireSchema = z.object({
  id,
  quote_no: z.string().nullable(),
  status: z.string(),
  total: z.string(),
  lead_id: id,
  sent_at: isoDateTime.nullable(),
});

const customerOrderWireSchema = z.object({
  id,
  order_no: z.string().nullable(),
  status: z.string(),
  total: z.string(),
  lead_id: id,
  submitted_at: isoDateTime.nullable(),
});

const customerDetailWireSchema = customerWireSchema.extend({
  leads: z.array(customerLeadWireSchema),
  quotations: z.array(customerQuotationWireSchema),
  orders: z.array(customerOrderWireSchema),
});

export type CustomerDetailWire = z.input<typeof customerDetailWireSchema>;

export interface CustomerDetail extends Customer {
  readonly leads: readonly {
    readonly id: string;
    readonly code: string;
    readonly stage: string;
    readonly source: string;
    readonly campaignName: string | null;
    readonly createdAt: string;
  }[];
  readonly quotations: readonly {
    readonly id: string;
    readonly quoteNo: string | null;
    readonly status: string;
    readonly total: string;
    readonly leadId: string;
    readonly sentAt: string | null;
  }[];
  readonly orders: readonly {
    readonly id: string;
    readonly orderNo: string | null;
    readonly status: string;
    readonly total: string;
    readonly leadId: string;
    readonly submittedAt: string | null;
  }[];
}

/** GET /customers/{id} and PATCH answer `{ data: CustomerDetail }`. */
export const customerDetailSchema = z
  .object({ data: customerDetailWireSchema })
  .transform(({ data }): CustomerDetail => ({
    ...toCustomer(data),
    leads: data.leads.map((lead) => ({
      id: lead.id,
      code: lead.inquiry_no,
      stage: lead.stage,
      source: lead.source,
      campaignName: lead.campaign_name,
      createdAt: lead.created_at,
    })),
    quotations: data.quotations.map((quotation) => ({
      id: quotation.id,
      quoteNo: quotation.quote_no,
      status: quotation.status,
      total: quotation.total,
      leadId: quotation.lead_id,
      sentAt: quotation.sent_at,
    })),
    orders: data.orders.map((order) => ({
      id: order.id,
      orderNo: order.order_no,
      status: order.status,
      total: order.total,
      leadId: order.lead_id,
      submittedAt: order.submitted_at,
    })),
  }));

/** One timeline entry: a lead's, naming the lead, or the customer's own (`lead_id` null). */
const customerTimelineEventSchema = z
  .looseObject({ lead_id: z.string().nullable(), inquiry_no: z.string().nullable().optional() })
  .transform((wire, ctx) => {
    const event = timelineEventSchema.safeParse(wire);
    if (!event.success) {
      ctx.addIssue({ code: "custom", message: "not a timeline event" });
      return z.NEVER;
    }
    return { ...event.data, leadId: wire.lead_id, leadCode: wire.inquiry_no ?? null };
  });

export type CustomerTimelineEvent = z.output<typeof customerTimelineEventSchema>;

/** GET /customers/{id}/timeline — newest first, one event at a time. */
export const customerTimelinePageSchema = cursorPageSchema(customerTimelineEventSchema);
export type CustomerTimelinePage = CursorPage<CustomerTimelineEvent>;

export interface CustomerListParams {
  readonly q: string;
  readonly territoryId: string | null;
}

/** PATCH /customers/{id} — only what changed. The mobile can't change here. */
export interface CustomerPatchRequest {
  readonly customer_type?: CustomerType;
  readonly name?: string;
  readonly email?: string | null;
  readonly territory_id?: string;
  readonly village?: string | null;
  readonly address?: string | null;
  readonly survey_no?: string | null;
  readonly consent_given?: boolean;
  readonly consent_channel?: ConsentChannel;
}
