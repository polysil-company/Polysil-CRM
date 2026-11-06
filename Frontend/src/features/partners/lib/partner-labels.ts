import { PARTNER_TYPES, type PartnerType } from "@/features/partners/api/partners.schemas";

export const PARTNER_TYPE_LABELS: Readonly<Record<PartnerType, string>> = {
  distributor: "Distributor",
  dealer: "Dealer",
  sub_dealer: "Sub-dealer",
};

/** Plural, for counts and filters: "3 dealers". */
export const PARTNER_TYPE_PLURALS: Readonly<Record<PartnerType, string>> = {
  distributor: "distributors",
  dealer: "dealers",
  sub_dealer: "sub-dealers",
};

/** The type a partner of this type sits under: a dealer's distributor; none for a distributor. */
export function parentTypeOf(type: PartnerType): PartnerType | null {
  const index = PARTNER_TYPES.indexOf(type);
  return index <= 0 ? null : (PARTNER_TYPES[index - 1] ?? null);
}

/** The type that sits under this one: a distributor's dealers; none under a sub-dealer. */
export function childTypeOf(type: PartnerType): PartnerType | null {
  return PARTNER_TYPES[PARTNER_TYPES.indexOf(type) + 1] ?? null;
}
