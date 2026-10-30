import { z } from "zod";

import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";

/**
 * CHNL-001…004 · Channel partners: distributors, their dealers and the dealers' sub-dealers
 * (`backend/docs/api/partners.md`). Every key is always present; null means "not set".
 * `credit_limit` and `payment_terms_days` are null unless the reader may edit partners.
 */

const id = z.string().min(1);

/** The order a partner sits in: a dealer under a distributor, a sub-dealer under a dealer. */
export const PARTNER_TYPES = ["distributor", "dealer", "sub_dealer"] as const;
export type PartnerType = (typeof PARTNER_TYPES)[number];
const partnerTypeSchema = z.enum(PARTNER_TYPES);

const partnerWireSchema = z.object({
  id,
  code: z.string(),
  name: z.string(),
  partner_type: partnerTypeSchema,
  /** Always the partner type (ADR-030). */
  price_tier: z.string(),
  parent: z.object({ id, name: z.string(), partner_type: z.string() }).nullable(),
  territory: z.object({ id, name: z.string(), level: z.string() }).nullable(),
  contact_name: z.string().nullable(),
  /** 91XXXXXXXXXX, no plus. */
  mobile: z.string().nullable(),
  email: z.string().nullable(),
  address: z.string().nullable(),
  gstin: z.string().nullable(),
  pan: z.string().nullable(),
  is_gst_registered: z.boolean(),
  /** Rupees, a decimal string. Stored, not enforced (H12). */
  credit_limit: z.string().nullable(),
  payment_terms_days: z.number().int().nullable(),
  is_active: z.boolean(),
  /** Active partner users anchored here. */
  users: z.number().int().nonnegative(),
  created_at: z.string().min(1),
});

export type PartnerWire = z.input<typeof partnerWireSchema>;

/** A partner, as screens read it. */
export interface Partner {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly type: PartnerType;
  readonly parent: { readonly id: string; readonly name: string; readonly type: string } | null;
  readonly territory: { readonly id: string; readonly name: string; readonly level: string } | null;
  readonly contactName: string | null;
  readonly mobile: string | null;
  readonly email: string | null;
  readonly address: string | null;
  readonly gstin: string | null;
  readonly pan: string | null;
  readonly gstRegistered: boolean;
  readonly creditLimit: string | null;
  readonly paymentTermsDays: number | null;
  readonly active: boolean;
  readonly users: number;
  readonly createdAt: string;
}

function toPartner(wire: z.output<typeof partnerWireSchema>): Partner {
  return {
    id: wire.id,
    code: wire.code,
    name: wire.name,
    type: wire.partner_type,
    parent:
      wire.parent === null
        ? null
        : { id: wire.parent.id, name: wire.parent.name, type: wire.parent.partner_type },
    territory: wire.territory,
    contactName: wire.contact_name,
    mobile: wire.mobile,
    email: wire.email,
    address: wire.address,
    gstin: wire.gstin,
    pan: wire.pan,
    gstRegistered: wire.is_gst_registered,
    creditLimit: wire.credit_limit,
    paymentTermsDays: wire.payment_terms_days,
    active: wire.is_active,
    users: wire.users,
    createdAt: wire.created_at,
  };
}

export const partnerPageSchema = cursorPageSchema(partnerWireSchema.transform(toPartner));
export type PartnerPage = CursorPage<Partner>;
export interface PartnerPageWire {
  readonly data: PartnerWire[];
  readonly meta: PageMetaWire;
}

export const partnerSchema = z
  .object({ data: partnerWireSchema })
  .transform(({ data }) => toPartner(data));

/** Close and reopen answer the partner and how many of its people are inactive. */
export const partnerStateSchema = z
  .object({
    data: partnerWireSchema.extend({
      /** Partner users anchored here who are inactive. Reopening restores none of them. */
      users_inactive: z.number().int().nonnegative(),
    }),
  })
  .transform(({ data }) => ({ partner: toPartner(data), usersInactive: data.users_inactive }));

export type PartnerStateChange = z.output<typeof partnerStateSchema>;

/** GET /partners and /partners/export filters, as the URL keeps them. */
export interface PartnerListParams {
  readonly q: string;
  readonly type: PartnerType | null;
  /** Children of this partner. */
  readonly parentId: string | null;
  /** null for every partner, open or closed. */
  readonly active: boolean | null;
  readonly cursor: string | null;
}

/** POST /partners */
export interface CreatePartnerRequest {
  /** The partner one type up; null for a distributor. */
  readonly parent_id: string | null;
  readonly partner_type: PartnerType;
  readonly code: string;
  readonly name: string;
  readonly territory_id: string;
  readonly contact_name: string | null;
  readonly mobile: string | null;
  readonly email: string | null;
  readonly address: string | null;
  readonly gstin: string | null;
  readonly pan: string | null;
  readonly is_gst_registered: boolean;
  /** Staff only. Rupees. */
  readonly credit_limit: string | null;
  /** Staff only. */
  readonly payment_terms_days: number | null;
}

/** PATCH /partners/{id}: only what changes. The type and the parent never change. */
export interface PatchPartnerRequest {
  readonly name?: string;
  readonly contact_name?: string | null;
  readonly mobile?: string | null;
  readonly email?: string | null;
  readonly address?: string | null;
  readonly gstin?: string | null;
  readonly pan?: string | null;
  readonly is_gst_registered?: boolean;
  readonly territory_id?: string;
  readonly credit_limit?: string | null;
  readonly payment_terms_days?: number | null;
}

/**
 * CHNL-006 · GET /gstin/{gstin} (FS-053): what a GSTIN says about itself, and the names the GST
 * record gives once the backend has a data provider (`lookup: found`). Until then it answers
 * `unavailable` and the names are typed by hand (GAP-292).
 */
export const gstinLookupSchema = z
  .object({
    data: z.object({
      gstin: z.string().min(1),
      valid: z.boolean(),
      /** Why it is not valid. */
      reason: z.string().nullable(),
      state_code: z.string().nullable(),
      pan: z.string().nullable(),
      lookup: z.enum(["found", "not_found", "unavailable"]),
      legal_name: z.string().nullish(),
      trade_name: z.string().nullish(),
      address: z.string().nullish(),
      status: z.string().nullish(),
    }),
  })
  .transform(({ data }) => ({
    gstin: data.gstin,
    valid: data.valid,
    reason: data.reason,
    pan: data.pan,
    lookup: data.lookup,
    legalName: data.legal_name?.trim() || null,
    tradeName: data.trade_name?.trim() || null,
    address: data.address?.trim() || null,
    status: data.status?.trim() || null,
  }));

export type GstinLookupWire = z.input<typeof gstinLookupSchema>;
export type GstinLookup = z.output<typeof gstinLookupSchema>;
