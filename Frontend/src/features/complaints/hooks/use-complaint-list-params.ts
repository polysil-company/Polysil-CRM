"use client";

import {
  createParser,
  parseAsArrayOf,
  parseAsBoolean,
  parseAsString,
  parseAsStringLiteral,
  useQueryStates,
} from "nuqs";

import {
  COMPLAINT_SEVERITIES,
  COMPLAINT_STATUSES,
  type ComplaintListParams,
} from "@/features/complaints/api/complaints.schemas";

const ID_PATTERN = /^[\w-]{1,64}$/;
const parseAsId = createParser({
  parse: (value: string) => (ID_PATTERN.test(value) ? value : null),
  serialize: (value: string) => value,
});

export const COMPLAINT_VIEWS = ["all", "mine"] as const;
export type ComplaintView = (typeof COMPLAINT_VIEWS)[number];

/**
 * CMPL-001 · The complaints list's place in the URL: the view (`?view=mine`, what waits on the
 * user), search, status, severity, type, late only and no owner — shareable as a link.
 */
export function useComplaintListParams(): {
  view: ComplaintView;
  params: ComplaintListParams;
  activeFilterCount: number;
  setView: (view: ComplaintView) => void;
  setFilters: (
    patch: Partial<Omit<ComplaintListParams, "awaitingMe" | "leadId" | "orderId">>,
  ) => void;
  resetFilters: () => void;
} {
  const [values, setValues] = useQueryStates({
    view: parseAsStringLiteral(COMPLAINT_VIEWS).withDefault("all"),
    q: parseAsString.withDefault(""),
    status: parseAsArrayOf(parseAsStringLiteral(COMPLAINT_STATUSES)).withDefault([]),
    severity: parseAsStringLiteral(COMPLAINT_SEVERITIES),
    type: parseAsId,
    late: parseAsBoolean.withDefault(false),
    unowned: parseAsBoolean.withDefault(false),
  });
  const mine = values.view === "mine";
  const params: ComplaintListParams = {
    // The queue is one page, oldest first: the filters don't apply to it.
    status: mine ? [] : [...new Set(values.status)],
    severity: mine ? null : values.severity,
    typeId: mine ? null : values.type,
    q: mine ? "" : values.q.trim(),
    breached: mine ? false : values.late,
    noOwner: mine ? false : values.unowned,
    awaitingMe: mine,
    leadId: null,
    orderId: null,
  };
  const activeFilterCount =
    (params.q === "" ? 0 : 1) +
    (params.status.length > 0 ? 1 : 0) +
    (params.severity === null ? 0 : 1) +
    (params.typeId === null ? 0 : 1) +
    (params.breached ? 1 : 0) +
    (params.noOwner ? 1 : 0);

  return {
    view: values.view,
    params,
    activeFilterCount,
    setView: (view) => {
      void setValues({ view: view === "all" ? null : view });
    },
    setFilters: (patch) => {
      void setValues({
        ...(patch.q === undefined ? {} : { q: patch.q === "" ? null : patch.q }),
        ...(patch.status === undefined
          ? {}
          : { status: patch.status.length === 0 ? null : [...patch.status] }),
        ...(patch.severity === undefined ? {} : { severity: patch.severity }),
        ...(patch.typeId === undefined ? {} : { type: patch.typeId }),
        ...(patch.breached === undefined ? {} : { late: patch.breached ? true : null }),
        ...(patch.noOwner === undefined ? {} : { unowned: patch.noOwner ? true : null }),
      });
    },
    resetFilters: () => {
      void setValues({
        q: null,
        status: null,
        severity: null,
        type: null,
        late: null,
        unowned: null,
      });
    },
  };
}
