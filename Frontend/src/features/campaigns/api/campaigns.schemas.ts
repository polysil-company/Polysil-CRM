import { z } from "zod";

/**
 * MKT-005, MKT-006 · Campaigns (FS-040; handover `campaigns.md`, `docs/api/campaigns.md`): the
 * fairs, meetings and drives that bring leads in. Marketing keeps them; any staff user picks one
 * on a lead or a QR code. Cost shows only with `campaigns.view`. Money is a decimal string.
 */

const id = z.string().min(1);
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const isoDate = z.iso.date();
const isoDateTime = z.iso.datetime({ offset: true });

export const CAMPAIGN_TYPES = [
  "exhibition",
  "agri_fair",
  "farmer_meeting",
  "dealer_meet",
  "promo_drive",
  "digital",
  "print",
  "other",
] as const;
export type CampaignType = (typeof CAMPAIGN_TYPES)[number];

const summaryWireSchema = z.object({
  leads: z.number().int(),
  won: z.number().int(),
  lost: z.number().int(),
  open: z.number().int(),
  /** Null without sales_orders. */
  sales_value: decimal.nullable(),
  /** Null without campaigns.view, or with no leads. */
  cost_per_lead: decimal.nullable(),
  /** Null without campaigns.view, or with no wins. */
  cost_per_won: decimal.nullable(),
});

const campaignWireSchema = z.object({
  id,
  name: z.string().min(1),
  /** One of CAMPAIGN_TYPES; an unknown one is kept and shown as "Other". */
  type: z.string().min(1),
  territory: z.object({ id, name: z.string(), level: z.string() }).nullable(),
  start_date: isoDate,
  /** Null: a one-day campaign. */
  end_date: isoDate.nullable(),
  /** Null unless you have campaigns.view. */
  cost_planned: decimal.nullable(),
  /** Null until entered, or without campaigns.view. */
  cost_actual: decimal.nullable(),
  description: z.string().nullable(),
  is_active: z.boolean(),
  /** Leads you can see that name it. */
  lead_count: z.number().int(),
  created_at: isoDateTime,
  updated_at: isoDateTime,
  /** Only on GET /campaigns/{id}. */
  summary: summaryWireSchema.nullish(),
});
export type CampaignWire = z.input<typeof campaignWireSchema>;

export interface CampaignSummary {
  readonly leads: number;
  readonly won: number;
  readonly lost: number;
  readonly open: number;
  readonly salesValue: string | null;
  readonly costPerLead: string | null;
  readonly costPerWon: string | null;
}

export interface Campaign {
  readonly id: string;
  readonly name: string;
  readonly type: CampaignType;
  readonly territory: { readonly id: string; readonly name: string; readonly level: string } | null;
  readonly startDate: string;
  readonly endDate: string | null;
  readonly costPlanned: string | null;
  readonly costActual: string | null;
  readonly description: string | null;
  readonly active: boolean;
  readonly leadCount: number;
  readonly summary: CampaignSummary | null;
}

function typeOf(value: string): CampaignType {
  return CAMPAIGN_TYPES.find((type) => type === value) ?? "other";
}

function toCampaign(wire: z.output<typeof campaignWireSchema>): Campaign {
  return {
    id: wire.id,
    name: wire.name,
    type: typeOf(wire.type),
    territory: wire.territory,
    startDate: wire.start_date,
    endDate: wire.end_date,
    costPlanned: wire.cost_planned,
    costActual: wire.cost_actual,
    description: wire.description,
    active: wire.is_active,
    leadCount: wire.lead_count,
    summary:
      wire.summary == null
        ? null
        : {
            leads: wire.summary.leads,
            won: wire.summary.won,
            lost: wire.summary.lost,
            open: wire.summary.open,
            salesValue: wire.summary.sales_value,
            costPerLead: wire.summary.cost_per_lead,
            costPerWon: wire.summary.cost_per_won,
          },
  };
}

export const campaignListSchema = z
  .object({ data: z.array(campaignWireSchema) })
  .transform(({ data }) => data.map(toCampaign));

export const campaignResponseSchema = z
  .object({ data: campaignWireSchema })
  .transform(({ data }) => toCampaign(data));

export interface CampaignListParams {
  /** true: only active ones (for a picker); false: only switched off; null: all. */
  readonly active: boolean | null;
  readonly type: CampaignType | null;
  /** Name contains; already trimmed. */
  readonly q: string;
}

export interface CampaignCreateRequest {
  readonly name: string;
  readonly type: CampaignType;
  readonly territory_id: string | null;
  readonly start_date: string;
  readonly end_date: string | null;
  readonly cost_planned: string;
  readonly cost_actual: string | null;
  readonly description: string | null;
}

export type CampaignPatchRequest = Partial<CampaignCreateRequest> & {
  readonly is_active?: boolean;
};
