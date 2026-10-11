import { z } from "zod";

/**
 * LEAD-013, LEAD-014 · The staff QR codes and the public enquiry page, as the backend serves
 * them (`backend/docs/api/leads.md` `/lead-qr-codes`, `backend/docs/api/public.md`, handover
 * `public-lead-capture-contract.md`).
 */

const id = z.string().min(1);
const isoDateTime = z.iso.datetime({ offset: true });

// ── QR codes (LEAD-013) ──────────────────────────────────────────────────────────

const qrCodeWireSchema = z.object({
  id,
  /** Six characters, no look-alikes. Never changes. */
  code: z.string().min(1),
  /** What the printed QR encodes: `<web app>/enquiry?qr=<code>`. Never changes. */
  url: z.string().min(1),
  label: z.string().min(1),
  campaign: z.string().nullable(),
  partner: z.object({ id, name: z.string(), partner_type: z.string() }).nullable(),
  territory: z.object({ id, name: z.string(), level: z.string() }).nullable(),
  is_active: z.boolean(),
  /** Leads this code has brought, in the caller's scope. */
  lead_count: z.number().int().nonnegative(),
  created_at: isoDateTime,
});

export type QrCodeWire = z.input<typeof qrCodeWireSchema>;

const qrCodeSchema = qrCodeWireSchema.transform((wire) => ({
  id: wire.id,
  code: wire.code,
  url: wire.url,
  label: wire.label,
  campaign: wire.campaign,
  partner: wire.partner,
  territory: wire.territory,
  isActive: wire.is_active,
  leadCount: wire.lead_count,
  createdAt: wire.created_at,
}));

export type QrCode = z.output<typeof qrCodeSchema>;

export const qrCodeListSchema = z
  .object({ data: z.array(qrCodeSchema) })
  .transform(({ data }) => data);

export const qrCodeResponseSchema = z.object({ data: qrCodeSchema }).transform(({ data }) => data);

/** POST /lead-qr-codes */
export interface CreateQrCodeRequest {
  readonly label: string;
  readonly campaign: string | null;
  readonly partner_id: string | null;
  readonly territory_id: string | null;
}

/** PATCH /lead-qr-codes/{id} — only what changes; `is_active: false` switches it off. */
export type PatchQrCodeRequest = Partial<CreateQrCodeRequest> & { readonly is_active?: boolean };

// ── the public enquiry page (LEAD-014) ────────────────────────────────────────────

export const publicLeadFormSchema = z
  .object({
    data: z.object({
      /** Null when the page was opened without a code. */
      qr: z
        .object({
          code: z.string().min(1),
          label: z.string(),
          campaign: z.string().nullable(),
          territory_id: z.string().nullable(),
        })
        .nullable(),
      states: z.array(z.object({ id, name: z.string() })),
      mis_systems: z.array(z.object({ code: z.string().min(1), name: z.string() })),
      inquiry_types: z.array(z.string()),
    }),
  })
  .transform(({ data }) => ({
    qr:
      data.qr === null
        ? null
        : {
            code: data.qr.code,
            label: data.qr.label,
            campaign: data.qr.campaign,
            territoryId: data.qr.territory_id,
          },
    states: data.states,
    systems: data.mis_systems,
    inquiryTypes: data.inquiry_types,
  }));

export type PublicLeadForm = z.output<typeof publicLeadFormSchema>;
export type PublicLeadFormWire = z.input<typeof publicLeadFormSchema>;

export const publicTerritoriesSchema = z
  .object({ data: z.array(z.object({ id, name: z.string(), level: z.string() })) })
  .transform(({ data }) => data);

export type PublicTerritory = z.output<typeof publicTerritoriesSchema>[number];

export const verifySentSchema = z
  .object({
    data: z.object({
      sent: z.boolean(),
      channel: z.literal("whatsapp"),
      expires_in: z.number().int().positive(),
      resend_after: z.number().int().nonnegative(),
    }),
  })
  .transform(({ data }) => ({ expiresIn: data.expires_in, resendAfter: data.resend_after }));

export type VerifySent = z.output<typeof verifySentSchema>;

/** POST /public/leads */
export interface PublicLeadRequest {
  readonly mobile: string;
  /** The six digits from WhatsApp. */
  readonly code: string;
  readonly farmer_name: string;
  /** A district or taluka, never a state. */
  readonly territory_id: string;
  readonly village: string | null;
  readonly mis_system: string;
  readonly inquiry_type: "commercial" | "subsidised" | "industrial";
  readonly note: string | null;
  readonly qr: string | null;
}

export const publicLeadResultSchema = z
  .object({ data: z.object({ inquiry_no: z.string().min(1), created: z.boolean() }) })
  .transform(({ data }) => ({ inquiryNo: data.inquiry_no, created: data.created }));

export type PublicLeadResult = z.output<typeof publicLeadResultSchema>;
