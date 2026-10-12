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
  | {
      readonly type: "assigned";
      readonly owner: AssignmentChange;
      readonly partner: AssignmentChange;
      /** On a handover, who held the lead before; null when not named. */
      readonly previousOwnerName: string | null;
    }
  | { readonly type: "updated"; readonly fields: readonly string[] }
  | {
      readonly type: "merged";
      readonly role: "survivor" | "loser";
      readonly otherLeadId: string;
      /** The other lead's inquiry number; null when the reader cannot see that lead. */
      readonly otherNumber: string | null;
    }
  | { readonly type: "duplicate-flagged"; readonly matches: readonly LeadRef[] }
  | { readonly type: "duplicate-dismissed"; readonly other: LeadRef | null }
  | { readonly type: "deleted" }
  | {
      readonly type: "approval";
      readonly decision: "approve" | "reject" | null;
      /** The step's role code: `district_manager`, `account_manager` … */
      readonly role: string | null;
    }
  | {
      /** The customer opened the quotation link: said without an actor (walk F-16). */
      readonly type: "customer-opened";
      readonly document: TimelineDocument | null;
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

/** Another lead an event names, with its inquiry number when the reader may see it. */
export interface LeadRef {
  readonly leadId: string | null;
  readonly number: string | null;
}

/** A quotation or sales order an event links to. */
export interface TimelineDocument {
  readonly kind: "quotation" | "order";
  readonly id: string;
  /**
   * "QT/GJ/2026-27/00003 · v2", "SO/GJ/2026-27/00041". A draft has no number yet: "draft
   * quotation v1", "draft order" (walk F-16).
   */
  readonly title: string;
}

/** How an assignment event touched a field: given a value, cleared, or left alone. */
export type ChangeKind = "set" | "cleared" | "unchanged";

/**
 * One side of an assignment: what happened, and the name the backend wrote beside the id
 * (BE-006). The name is null on events from before BE-006, and for someone the backend could
 * not name, so the sentence falls back to "changed the owner".
 */
export interface AssignmentChange {
  readonly kind: ChangeKind;
  readonly name: string | null;
}

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
    const number = optionalText.parse(payload.quote_no) ?? null;
    const v = version.parse(payload.version) ?? null;
    if (number === null) {
      return { kind: "quotation", id: quotationId, title: `draft quotation v${String(v ?? 1)}` };
    }
    return {
      kind: "quotation",
      id: quotationId,
      title: v !== null && v > 1 ? `${number} · v${String(v)}` : number,
    };
  }
  const orderId = optionalText.parse(payload.order_id) ?? null;
  if (orderId !== null) {
    return {
      kind: "order",
      id: orderId,
      title: optionalText.parse(payload.order_no) ?? "draft order",
    };
  }
  return null;
}

const DOCUMENT_KIND = /^(quotation|order|dispatch)\./;

/** "quotation.sent" → "Quotation sent" — for a kind this file does not know yet. */
export function labelForUnknownKind(kind: string): string {
  return OTHER_KIND_LABELS[kind] ?? humanizeCode(kind.replace(/\./g, " "));
}

function changeOf(
  payload: Readonly<Record<string, unknown>>,
  key: string,
  nameKey: string,
): AssignmentChange {
  if (!(key in payload)) {
    return { kind: "unchanged", name: null };
  }
  const set = typeof payload[key] === "string" && payload[key] !== "";
  return {
    kind: set ? "set" : "cleared",
    name: set ? (optionalText.parse(payload[nameKey]) ?? null) : null,
  };
}

/** A match in `lead.duplicate_flagged`, or the other lead of a dismissal. */
function leadRefOf(raw: unknown): LeadRef {
  const fields = z.record(z.string(), z.unknown()).catch({}).parse(raw);
  return {
    leadId: optionalText.parse(fields.lead_id) ?? null,
    number: optionalText.parse(fields.inquiry_no) ?? null,
  };
}

/** "POL/GJ/2026-27/00083" → "00083": enough to tell leads apart in a list of them. */
export function shortInquiryNumber(number: string): string {
  return number.split("/").at(-1) ?? number;
}

/**
 * Whether an event earns its own line. A decision on a quotation's discount is written twice:
 * as the approval step and as the discount's outcome; the second says it, so the first is left
 * out (walk F-16). An order's decisions have one line each.
 */
export function isShownOnTimeline(event: TimelineEvent): boolean {
  return !(event.kind === "approval.decided" && typeof event.payload.quotation_id === "string");
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
        owner: changeOf(payload, "owner_user_id", "owner_name"),
        partner: changeOf(payload, "assigned_partner_id", "partner_name"),
        previousOwnerName: optionalText.parse(payload.previous_owner_name) ?? null,
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
        return {
          type: "merged",
          role: "survivor",
          otherLeadId: loser,
          otherNumber: optionalText.parse(payload.loser_inquiry_no) ?? null,
        };
      }
      if (loser === leadId && survivor) {
        return {
          type: "merged",
          role: "loser",
          otherLeadId: survivor,
          otherNumber: optionalText.parse(payload.survivor_inquiry_no) ?? null,
        };
      }
      return { type: "other", label: "Leads merged" };
    }

    case "lead.duplicate_flagged": {
      const matches = z.array(z.unknown()).catch([]).parse(payload.matches);
      return { type: "duplicate-flagged", matches: matches.map(leadRefOf) };
    }

    case "lead.duplicate_dismissed": {
      const other = leadRefOf({
        lead_id: payload.other_lead_id,
        inquiry_no: payload.other_inquiry_no,
      });
      return {
        type: "duplicate-dismissed",
        other: other.leadId === null && other.number === null ? null : other,
      };
    }

    case "lead.deleted":
      return { type: "deleted" };

    case "approval.decided": {
      const decision =
        payload.decision === "approve" || payload.decision === "reject" ? payload.decision : null;
      return { type: "approval", decision, role: optionalText.parse(payload.role) ?? null };
    }
    case "quotation.viewed":
      return { type: "customer-opened", document: documentOf(payload) };

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

/**
 * LEAD-008 · An assignment, as the rest of a sentence that starts with the actor's name:
 * "assigned the lead to Ravi Joshi and made Shree Agro the channel partner". Events without
 * names (before BE-006) still read: "changed the owner".
 */
export function assignmentSentence({
  owner,
  partner,
  previousOwnerName,
}: Extract<TimelineEntry, { type: "assigned" }>): string {
  if (
    owner.kind === "set" &&
    partner.kind === "set" &&
    owner.name === null &&
    partner.name === null
  ) {
    return "changed the owner and the channel partner";
  }
  const parts: string[] = [];
  if (owner.kind === "set") {
    parts.push(
      owner.name === null
        ? "changed the owner"
        : previousOwnerName === null
          ? `assigned the lead to ${owner.name}`
          : `handed the lead from ${previousOwnerName} to ${owner.name}`,
    );
  }
  if (owner.kind === "cleared") {
    parts.push(
      previousOwnerName === null ? "unassigned the owner" : `unassigned ${previousOwnerName}`,
    );
  }
  if (partner.kind === "set") {
    parts.push(
      partner.name === null
        ? "changed the channel partner"
        : `made ${partner.name} the channel partner`,
    );
  }
  if (partner.kind === "cleared") {
    parts.push("removed the channel partner");
  }
  return parts.length === 0 ? "updated the assignment" : parts.join(" and ");
}
