"use client";

import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";

import { PARTNER_TYPES, type PartnerListParams } from "@/features/partners/api/partners.schemas";

export const PARTNER_STATUSES = ["open", "closed"] as const;
export type PartnerStatus = (typeof PARTNER_STATUSES)[number];

const ID_PATTERN = /^[0-9a-f-]{8,64}$/i;

/**
 * CHNL-001 · The partner list's place in the URL: search, type, open or closed, and the
 * partner they sit under — shareable as a link. Open partners by default.
 */
export function usePartnerListParams(): {
  params: Omit<PartnerListParams, "cursor">;
  status: PartnerStatus | "all";
  activeFilterCount: number;
  setFilters: (patch: {
    q?: string;
    type?: PartnerListParams["type"];
    parentId?: string | null;
    status?: PartnerStatus | "all";
  }) => void;
  resetFilters: () => void;
} {
  const [values, setValues] = useQueryStates({
    q: parseAsString.withDefault(""),
    type: parseAsStringLiteral(PARTNER_TYPES),
    parent: parseAsString,
    status: parseAsStringLiteral([...PARTNER_STATUSES, "all"] as const).withDefault("open"),
  });
  const parentId = values.parent !== null && ID_PATTERN.test(values.parent) ? values.parent : null;
  const params = {
    q: values.q.trim(),
    type: values.type,
    parentId,
    active: values.status === "all" ? null : values.status === "open",
  };
  const activeFilterCount =
    (params.q === "" ? 0 : 1) +
    (params.type === null ? 0 : 1) +
    (parentId === null ? 0 : 1) +
    (values.status === "open" ? 0 : 1);

  return {
    params,
    status: values.status,
    activeFilterCount,
    setFilters: (patch) => {
      void setValues({
        ...(patch.q === undefined ? {} : { q: patch.q === "" ? null : patch.q }),
        ...(patch.type === undefined ? {} : { type: patch.type }),
        ...(patch.parentId === undefined ? {} : { parent: patch.parentId }),
        ...(patch.status === undefined
          ? {}
          : { status: patch.status === "open" ? null : patch.status }),
      });
    },
    resetFilters: () => {
      void setValues({ q: null, type: null, parent: null, status: null });
    },
  };
}
