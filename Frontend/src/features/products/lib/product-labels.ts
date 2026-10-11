import type {
  ChannelTier,
  PriceList,
  ProvisionalField,
  QuotationCategory,
} from "@/features/products/api/products.schemas";
import { formatFullDate, todayInIndia } from "@/lib/format";

/** MSTR-004…006 · The product master in words. */

export const QUOTATION_CATEGORY_LABELS: Readonly<Record<QuotationCategory, string>> = {
  head: "Head unit",
  field: "Field",
  both: "Head unit or field",
};

export const PROVISIONAL_LABELS: Readonly<Record<ProvisionalField, string>> = {
  hsn_code: "HSN code",
  gst_slab: "GST slab",
  mrp: "MRP",
  pack_multiple: "pack multiple",
};

export const TIER_LABELS: Readonly<Record<ChannelTier, string>> = {
  distributor: "Distributors",
  dealer: "Dealers",
  sub_dealer: "Sub-dealers",
  farmer: "Farmers (retail)",
};

/** "Every state · every tier", "Gujarat · Dealers". */
export function scopeOf(list: Pick<PriceList, "state" | "tier">): string {
  return `${list.state?.name ?? "Every state"} · ${list.tier === null ? "every tier" : TIER_LABELS[list.tier]}`;
}

/** "in Gujarat, for dealers", "in every state, for every tier": the scope inside a sentence. */
export function scopeInSentence(list: Pick<PriceList, "state" | "tier">): string {
  const tier = list.tier === null ? "every tier" : TIER_LABELS[list.tier].toLowerCase();
  return `in ${list.state?.name ?? "every state"}, for ${tier}`;
}

export type ListPhase = "draft" | "scheduled" | "in-force" | "ended";

/** Where a list stands today: a draft, published but not started, in force, or over. */
export function phaseOf(
  list: Pick<PriceList, "status" | "from" | "to">,
  today = todayInIndia(),
): ListPhase {
  if (list.status === "draft") return "draft";
  if (list.to !== null && list.to <= today) return "ended";
  if (list.from > today) return "scheduled";
  return "in-force";
}

export const PHASE_LABELS: Readonly<Record<ListPhase, string>> = {
  draft: "Draft",
  scheduled: "Published, starts later",
  "in-force": "In force",
  ended: "Ended",
};

/** "1 Apr 2026": a calendar day, read as India's. */
export function dayText(day: string): string {
  return formatFullDate(`${day}T12:00:00+05:30`);
}

/** "From 1 Apr 2026", "1 Apr 2025 to 31 Mar 2026": `to` is exclusive, so the last day is before it. */
export function windowOf(from: string, to: string | null): string {
  if (to === null) return `From ${dayText(from)}`;
  const last = new Date(`${to}T00:00:00Z`);
  last.setUTCDate(last.getUTCDate() - 1);
  return `${dayText(from)} to ${dayText(last.toISOString().slice(0, 10))}`;
}

/** "18 %", "0.25 %": the slab as people read it. */
export function slabText(slab: string): string {
  return `${String(Number(slab))} %`;
}

/** A rate as typed: a positive amount with at most two decimals, or empty for no rate. */
export function rateProblem(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  if (!/^\d+(\.\d+)?$/.test(trimmed)) return "A number, like 103.19.";
  if ((trimmed.split(".")[1]?.length ?? 0) > 2)
    return "At most two decimals: rates aren't rounded.";
  if (Number(trimmed) <= 0) return "More than 0. Leave it empty for no rate.";
  return null;
}
