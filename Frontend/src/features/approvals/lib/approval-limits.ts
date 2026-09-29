import {
  DISCOUNT_LIMIT_ROLES,
  ORDER_LIMIT_ROLES,
  type ApprovalDocType,
  type LimitRole,
  type Threshold,
} from "@/features/approvals/api/approvals.schemas";
import { formatRate } from "@/features/quotations/lib/quotation-labels";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";

/**
 * APPR-002 · The approval limits as ladders: an order's managers by value, and a quotation's
 * discount from the officer's own limit up to Admin-Sales. The backend checks every rule
 * (backend/docs/api/approvals.md, `put_threshold`); these only explain them before saving.
 */

/** The roles of a document's ladder, lowest first. */
export function ladderRoles(docType: ApprovalDocType): readonly LimitRole[] {
  return docType === "sales_order" ? ORDER_LIMIT_ROLES : DISCOUNT_LIMIT_ROLES;
}

/** One step of a ladder: the role and its row, or no row yet. */
export interface LadderStep {
  readonly role: LimitRole;
  readonly row: Threshold | null;
}

/** A ladder — company-wide (`territoryId` null) or one territory's own rows. */
export function ladderFor(
  rows: readonly Threshold[],
  docType: ApprovalDocType,
  territoryId: string | null,
): LadderStep[] {
  return ladderRoles(docType).map((role) => ({
    role,
    row:
      rows.find(
        (row) =>
          row.docType === docType &&
          row.role === role &&
          (row.territory?.id ?? null) === territoryId,
      ) ?? null,
  }));
}

/** The territories with rows of their own for a document, by name. */
export function overrideTerritories(
  rows: readonly Threshold[],
  docType: ApprovalDocType,
): NonNullable<Threshold["territory"]>[] {
  const seen = new Map<string, NonNullable<Threshold["territory"]>>();
  for (const row of rows) {
    if (row.docType === docType && row.territory !== null) {
      seen.set(row.territory.id, row.territory);
    }
  }
  return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Only the top of a ladder may have no ceiling: a discount below Admin-Sales without a limit
 * would switch the gate off for that role, and an order's lower managers always stop somewhere.
 */
export function mayBeUnlimited(docType: ApprovalDocType, role: LimitRole): boolean {
  return ladderRoles(docType).at(-1) === role;
}

/** What a new limit must sit between: above the level below, under the level above. */
export interface LimitBounds {
  /** The nearest lower level's limit; the new one must be above it. */
  readonly above: number | null;
  /** The nearest higher level's limit; the new one must be under it. */
  readonly under: number | null;
}

export function boundsFor(ladder: readonly LadderStep[], role: LimitRole): LimitBounds {
  const index = ladder.findIndex((step) => step.role === role);
  const amountOf = (step: LadderStep | undefined): number | null =>
    step?.row?.maxAmount == null ? null : Number(step.row.maxAmount);
  const lower = ladder
    .slice(0, Math.max(0, index))
    .map(amountOf)
    .filter((value) => value !== null);
  const higher = ladder
    .slice(index + 1)
    .map(amountOf)
    .filter((value) => value !== null);
  return { above: lower.at(-1) ?? null, under: higher.at(0) ?? null };
}

/** "Up to ₹1,00,000" or "Up to 10%"; "No limit" without a ceiling. */
export function formatLimit(amount: string | null, unit: Threshold["unit"]): string {
  if (amount === null) {
    return "No limit";
  }
  return unit === "inr" ? `Up to ${formatInr(amount)}` : `Up to ${formatRate(amount)}`;
}

function formatBound(value: number, unit: Threshold["unit"]): string {
  return unit === "inr" ? formatInr(value.toFixed(2)) : formatRate(value.toFixed(2));
}

/** "Above ₹1,00,000 and under ₹5,00,000" — what the form asks for, in words. */
export function boundsHint(bounds: LimitBounds, unit: Threshold["unit"]): string | null {
  const parts = [
    bounds.above === null ? null : `above ${formatBound(bounds.above, unit)}`,
    bounds.under === null ? null : `under ${formatBound(bounds.under, unit)}`,
  ].filter((part) => part !== null);
  if (parts.length === 0) {
    return null;
  }
  const text = parts.join(" and ");
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}, to keep each level above the one below.`;
}

/** The bound a typed limit breaks, in words; null when it fits. */
export function outOfBounds(
  value: number,
  bounds: LimitBounds,
  unit: Threshold["unit"],
): string | null {
  if (bounds.above !== null && value <= bounds.above) {
    return `Must be above ${formatBound(bounds.above, unit)}, the level below`;
  }
  if (bounds.under !== null && value >= bounds.under) {
    return `Must be under ${formatBound(bounds.under, unit)}, the level above`;
  }
  return null;
}

/** A refused save: a message for the amount field, or one for the dialog. */
export interface LimitRefusal {
  readonly field: string | null;
  readonly title: string;
  readonly message: string;
}

export function limitRefusal(error: unknown): LimitRefusal {
  if (isApiError(error) && error.code === "thresholds_not_increasing") {
    return {
      field: "Must be above the level below and under the level above",
      title: "The levels would be out of order",
      message: "Someone may have changed another level meanwhile. The limits now show the latest.",
    };
  }
  if (isApiError(error) && error.status === 403) {
    return {
      field: null,
      title: "Only an administrator changes approval limits",
      message: "Ask an administrator to make this change.",
    };
  }
  const field = readFieldErrors(error)?.max_amount ?? null;
  const view = toUserFacingError(error);
  return { field, title: view.title, message: view.description };
}
