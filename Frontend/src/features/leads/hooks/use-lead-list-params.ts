"use client";

import {
  createParser,
  parseAsArrayOf,
  parseAsInteger,
  parseAsString,
  parseAsStringLiteral,
  useQueryStates,
} from "nuqs";

import {
  LEAD_INQUIRY_TYPES,
  LEAD_PAGE_SIZES,
  LEAD_SORT_FIELDS,
  LEAD_STAGES,
  MAX_LEAD_AREAS,
  SORT_ORDERS,
  type LeadInquiryType,
  type LeadListParams,
  type LeadSortField,
  type LeadStage,
  type SortOrder,
} from "@/features/leads/api/leads.schemas";

const DEFAULT_PAGE_SIZE = LEAD_PAGE_SIZES[0];

/**
 * Administrators write these codes, so only their shape is checked, never their spelling:
 * letters, digits, `_`, `-` and `.` ("agri_fair", "agri-fair", "qr.code"). Anything else is
 * URL junk and is dropped. A code the backend does not know is refused by the backend.
 */
const LOOKUP_CODE_PATTERN = /^[\w.-]{1,64}$/;

const parseAsLookupCode = createParser({
  parse: (value: string) => (LOOKUP_CODE_PATTERN.test(value) ? value : null),
  serialize: (value: string) => value,
});

/** A territory id from GET /leads/areas: a UUID or similar, never a comma. */
const AREA_ID_PATTERN = /^[\w-]{1,64}$/;
const parseAsAreaId = createParser({
  parse: (value: string) => (AREA_ID_PATTERN.test(value) ? value : null),
  serialize: (value: string) => value,
});

/**
 * URL ⇄ state parsers. Filters, sort and page live in the URL, so a filtered page can be
 * bookmarked or sent to a colleague. Defaults are left out of the URL.
 *
 * The backend pages with cursors, not page numbers: `cursors` keeps the cursor of every page
 * the reader moved forward through, so page N is the (N-1)th cursor and "previous" drops the
 * last one. Cursors are base64url, which never contains the list's comma separator.
 */
export const leadListSearchParams = {
  cursors: parseAsArrayOf(parseAsString).withDefault([]),
  pageSize: parseAsInteger.withDefault(DEFAULT_PAGE_SIZE),
  sort: parseAsStringLiteral(LEAD_SORT_FIELDS).withDefault("createdAt"),
  order: parseAsStringLiteral(SORT_ORDERS).withDefault("desc"),
  q: parseAsString.withDefault(""),
  stage: parseAsArrayOf(parseAsStringLiteral(LEAD_STAGES)).withDefault([]),
  source: parseAsLookupCode,
  type: parseAsStringLiteral(LEAD_INQUIRY_TYPES),
  area: parseAsArrayOf(parseAsAreaId).withDefault([]),
};

export interface LeadFilterPatch {
  readonly q?: string;
  readonly stage?: readonly LeadStage[];
  readonly source?: string | null;
  readonly type?: LeadInquiryType | null;
  readonly areas?: readonly string[];
}

export interface LeadListParamsControls {
  readonly params: LeadListParams;
  /** 0 on the first page, one more for each page moved forward. */
  readonly pageIndex: number;
  /** Active filters, including a search. */
  readonly activeFilterCount: number;
  /** Changing a filter returns to the first page: cursors belong to one exact list. */
  setFilters: (patch: LeadFilterPatch) => void;
  setSort: (sort: LeadSortField, order: SortOrder) => void;
  /** Moves forward with the current page's `nextCursor`. */
  nextPage: (cursor: string) => void;
  previousPage: () => void;
  firstPage: () => void;
  setPageSize: (pageSize: number) => void;
  resetFilters: () => void;
}

function normalizePageSize(value: number): number {
  return LEAD_PAGE_SIZES.find((size) => size === value) ?? DEFAULT_PAGE_SIZE;
}

export function useLeadListParams(): LeadListParamsControls {
  const [values, setValues] = useQueryStates(leadListSearchParams, {
    history: "replace",
    clearOnDefault: true,
  });

  const cursors = values.cursors.filter((cursor) => cursor !== "");
  const params: LeadListParams = {
    cursor: cursors.at(-1) ?? null,
    pageSize: normalizePageSize(values.pageSize),
    sort: values.sort,
    order: values.order,
    // The search field already trims; a hand-edited URL may not.
    q: values.q.trim(),
    stage: values.stage,
    source: values.source,
    type: values.type,
    // A hand-edited URL may repeat an area or carry more than the backend takes.
    areas: [...new Set(values.area)].slice(0, MAX_LEAD_AREAS),
  };

  const activeFilterCount = [
    params.q !== "",
    params.stage.length > 0,
    params.source !== null,
    params.type !== null,
    params.areas.length > 0,
  ].filter(Boolean).length;

  return {
    params,
    pageIndex: cursors.length,
    activeFilterCount,
    setFilters: (patch) => {
      void setValues({
        cursors: null,
        ...(patch.q === undefined ? {} : { q: patch.q }),
        ...(patch.stage === undefined ? {} : { stage: [...patch.stage] }),
        ...(patch.source === undefined ? {} : { source: patch.source }),
        ...(patch.type === undefined ? {} : { type: patch.type }),
        ...(patch.areas === undefined ? {} : { area: [...patch.areas] }),
      });
    },
    setSort: (sort, order) => {
      void setValues({ sort, order, cursors: null });
    },
    nextPage: (cursor) => {
      void setValues({ cursors: [...cursors, cursor] });
    },
    previousPage: () => {
      void setValues({ cursors: cursors.slice(0, -1) });
    },
    firstPage: () => {
      void setValues({ cursors: null });
    },
    setPageSize: (pageSize) => {
      void setValues({ pageSize: normalizePageSize(pageSize), cursors: null });
    },
    resetFilters: () => {
      void setValues({ q: null, stage: null, source: null, type: null, area: null, cursors: null });
    },
  };
}
