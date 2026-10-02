import { z } from "zod";

import {
  LEAD_STAGES,
  type LeadStage,
  type TimelineEvent,
} from "@/features/leads/api/leads.schemas";
import { humanizeCode } from "@/features/lookups/lib/lookup-labels";

/**
 * LEAD-005 · What one timeline event means, read from its free-form `payload`.
 *
 * The backend writes each kind's payload itself (api/services/leads.py and migration 006),
 * so every field is read defensively: a missing or oddly-typed field becomes null, and an
 * unknown kind — a quotation or order event, or one added later — becomes `other` with a
 * readable label. The timeline never drops an event for its payload.
 */
export type TimelineEntry =
  | { readonly type: "created"; readonly source: string | null }
  | { readonly type: "note"; readonly note: string }
  | {
      readonly type: "stage";
      readonly from: LeadStage | null;
      readonly to: LeadStage | null;
      readonly lostReasonId: string | null;
      readonly lostNote: string | null;
    }
  | { readonly type: "reopened"; readonly to: LeadStage | null; readonly note: string | null }
  | { readonly type: "assigned"; readonly owner: ChangeKind; readonly partner: ChangeKind }
  | { readonly type: "updated"; readonly fields: readonly string[] }
  | { readonly type: "merged"; readonly role: "survivor" | "loser"; readonly otherLeadId: string }
  | { readonly type: "duplicate-flagged"; readonly count: number }
  | { readonly type: "duplicate-dismissed" }
  | { readonly type: "deleted" }
  | {
      readonly type: "approval";
      readonly decision: "approve" | "reject" | null;
      /** The step's role code: `district_manager`, `account_manager` … */
      readonly role: string | null;
    }
  | {
      readonly type: "document";
      readonly label: string;
      /** The quotation or order the event is about, when the backend names it. */
      readonly document: TimelineDocument | null;
      /** A dispatch's number, on dispatch events. */
      readonly dispatchNo: string | null;
    }
  | { readonly type: "other"; readonly label: string };

/** A quotation or sales order an event links to. */
export interface TimelineDocument {
  readonly kind: "quotation" | "order";
  readonly id: string;
  /** "QT/GJ/2026-27/00003 · v2", "SO/GJ/2026-27/00041"; "Draft" when it has no number yet. */
  readonly title: string;
}

/** How an assignment event touched a field: given a value, cleared, or left alone. */
export type ChangeKind = "set" | "cleared" | "unchanged";

const text = z.string().trim().min(1);
const optionalText = text.nullish().catch(null);
const stage = z.enum(LEAD_STAGES).nullish().catch(null);

/** Field names in `lead.updated`'s `changed`, as a sentence reads them. */
const UPDATED_FIELD_LABELS: Readonly<Record<string, string>> = {
  farmer_name: "farmer name",
  mobile: "mobile",
  email: "email",
  village: "village",
  inquiry_type: "inquiry type",
  mis_system: "irrigation system",
  source: "source",
  estimated_value: "estimated value",
  territory_id: "territory",
};

/** Events from other modules that appear on a lead's timeline. */
const OTHER_KIND_LABELS: Readonly<Record<string, string>> = {
  "quotation.created": "Quotation drafted",
  "quotation.updated": "Quotation edited",
  "quotation.lines_replaced": "Quotation items changed",
  "quotation.sent": "Quotation sent",
  "quotation.viewed": "Quotation opened by the customer",
  "quotation.accepted": "Quotation accepted",
  "quotation.rejected": "Quotation rejected",
  "quotation.negotiation": "Quotation in negotiation",
  "quotation.expired": "Quotation expired",
  "quotation.revised": "Quotation revised",
  "quotation.deleted": "Quotation deleted",
  "quotation.approval_requested": "Quotation discount approval asked",
  "quotation.approval_approved": "Quotation discount approved",
  "quotation.approval_returned": "Quotation discount approval refused",
  "quotation.approval_cancelled": "Quotation discount approval cancelled",
  "order.created": "Sales order created",
  "order.updated": "Sales order edited",
  "order.lines_replaced": "Sales order items changed",
  "order.submitted": "Sales order submitted",
  "order.approved": "Sales order approved",
  "order.returned": "Sales order returned for changes",
  "order.cancelled": "Sales order cancelled",
  "order.closed_short": "Sales order closed short",
  "order.confirmed": "Customer told of the sales order",
  "order.deleted": "Draft sales order deleted",
  "dispatch.recorded": "Dispatch recorded",
  "dispatch.voided": "Dispatch voided",
  "approval.decided": "Approval decided",
};

const version = z.number().int().positive().nullish().catch(null);

/**
 * The quotation or order an event names: quotation events carry `quotation_id`, `quote_no`
 * and `version` (BE-017); order events carry `order_id` and `order_no` once the backend
 * adds them (BE-020) — until then they name no order.
 */
function documentOf(payload: Readonly<Record<string, unknown>>): TimelineDocument | null {
  const quotationId = optionalText.parse(payload.quotation_id) ?? null;
  if (quotationId !== null) {
    const number = optionalText.parse(payload.quote_no) ?? "Draft";
    const v = version.parse(payload.version) ?? null;
    return {
      kind: "quotation",
      id: quotationId,
      title: v !== null && v > 1 ? `${number} · v${String(v)}` : number,
    };
  }
  const orderId = optionalText.parse(payload.order_id) ?? null;
  if (orderId !== null) {
    return { kind: "order", id: orderId, title: optionalText.parse(payload.order_no) ?? "Draft" };
  }
  return null;
}

const DOCUMENT_KIND = /^(quotation|order|dispatch)\./;

/** "quotation.sent" → "Quotation sent" — for a kind this file does not know yet. */
export function labelForUnknownKind(kind: string): string {
  return OTHER_KIND_LABELS[kind] ?? humanizeCode(kind.replace(/\./g, " "));
}

function changeOf(payload: Readonly<Record<string, unknown>>, key: string): ChangeKind {
  if (!(key in payload)) {
    return "unchanged";
  }
  return typeof payload[key] === "string" && payload[key] !== "" ? "set" : "cleared";
}

/** Turns one event into the entry the timeline renders. `leadId` is the lead on screen. */
export function toTimelineEntry(event: TimelineEvent, leadId: string): TimelineEntry {
  const { payload } = event;

  switch (event.kind) {
    case "lead.created":
      return { type: "created", source: optionalText.parse(payload.source) ?? null };

    case "lead.note_added": {
      const note = optionalText.parse(payload.note);
      return note ? { type: "note", note } : { type: "other", label: "Note added" };
    }

    case "lead.stage_changed":
      return {
        type: "stage",
        from: stage.parse(payload.from) ?? null,
        to: stage.parse(payload.to) ?? null,
        lostReasonId: optionalText.parse(payload.lost_reason_id) ?? null,
        lostNote: optionalText.parse(payload.lost_note) ?? null,
      };

    case "lead.reopened":
      return {
        type: "reopened",
        to: stage.parse(payload.to) ?? null,
        note: optionalText.parse(payload.note) ?? null,
      };

    case "lead.assigned":
      return {
        type: "assigned",
        owner: changeOf(payload, "owner_user_id"),
        partner: changeOf(payload, "assigned_partner_id"),
      };

    case "lead.updated": {
      const changed = z.record(z.string(), z.unknown()).catch({}).parse(payload.changed);
      return {
        type: "updated",
        fields: Object.keys(changed).map((key) => UPDATED_FIELD_LABELS[key] ?? humanizeCode(key)),
      };
    }

    case "lead.merged": {
      const survivor = optionalText.parse(payload.survivor);
      const loser = optionalText.parse(payload.loser);
      if (survivor === leadId && loser) {
        return { type: "merged", role: "survivor", otherLeadId: loser };
      }
      if (loser === leadId && survivor) {
        return { type: "merged", role: "loser", otherLeadId: survivor };
      }
      return { type: "other", label: "Leads merged" };
    }

    case "lead.duplicate_flagged": {
      const matches = z.array(z.unknown()).catch([]).parse(payload.matches);
      return { type: "duplicate-flagged", count: matches.length };
    }

    case "lead.duplicate_dismissed":
      return { type: "duplicate-dismissed" };

    case "lead.deleted":
      return { type: "deleted" };

    case "approval.decided": {
      const decision =
        payload.decision === "approve" || payload.decision === "reject" ? payload.decision : null;
      return { type: "approval", decision, role: optionalText.parse(payload.role) ?? null };
    }
    default:
      if (DOCUMENT_KIND.test(event.kind)) {
        return {
          type: "document",
          label: labelForUnknownKind(event.kind),
          document: documentOf(payload),
          dispatchNo: optionalText.parse(payload.dispatch_no) ?? null,
        };
      }
      return { type: "other", label: labelForUnknownKind(event.kind) };
  }
}

/** "farmer name, mobile and village" */
export function joinFields(fields: readonly string[]): string {
  if (fields.length <= 1) {
    return fields[0] ?? "";
  }
  return `${fields.slice(0, -1).join(", ")} and ${fields.at(-1) ?? ""}`;
}
