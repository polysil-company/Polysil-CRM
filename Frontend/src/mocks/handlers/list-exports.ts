import { http } from "msw";

import { buildApiUrl, type ApiPath } from "@/lib/api/url";

import { mockWorkbook } from "./shared";

/**
 * FS-081 · `GET <list>/export` for the 24 lists that gained one. The real file holds exactly the
 * rows the list shows for its filters; the mock sends the backend's column headings and one
 * sample row, as Excel or CSV. The screens never ask a list for PDF.
 * Registered before the lists' own handlers, so `/products/export` isn't read as a product id.
 */
const LIST_EXPORTS: readonly {
  readonly path: ApiPath;
  readonly stem: string;
  readonly headers: readonly string[];
}[] = [
  {
    path: "/products/export",
    stem: "products",
    headers: [
      "Item code",
      "Description",
      "Category",
      "Quotation block",
      "Unit",
      "HSN",
      "GST slab",
      "MRP",
      "Pack multiple",
      "Subsidy eligible",
      "Active",
      "Stand-in fields",
    ],
  },
  {
    path: "/tax-rates/export",
    stem: "tax-rates",
    headers: ["HSN", "GST rate", "From", "To", "Active"],
  },
  {
    path: "/price-lists/export",
    stem: "price-lists",
    headers: [
      "Name",
      "State",
      "Channel tier",
      "Sale type",
      "Status",
      "Published",
      "From",
      "To",
      "Active",
      "Stand-in",
      "Items",
      "Unpriced",
    ],
  },
  {
    path: "/price-lists/:listId/items/export",
    stem: "price-list-items",
    headers: ["Product", "Unit", "Rate", "Product active"],
  },
  {
    path: "/customers/export",
    stem: "customers",
    headers: [
      "Name",
      "Type",
      "Mobile",
      "Email",
      "Territory",
      "Village",
      "Address",
      "Survey no.",
      "Consent given",
      "Consent channel",
      "Leads",
      "Created",
    ],
  },
  {
    path: "/stock/export",
    stem: "stock",
    headers: ["Warehouse", "Product code", "Product", "Unit", "On hand", "Committed", "Available"],
  },
  {
    path: "/stock/movements/export",
    stem: "stock-movements",
    headers: [
      "When",
      "Warehouse",
      "Product code",
      "Product",
      "Quantity",
      "Kind",
      "Reference",
      "Dispatch",
      "Order",
      "Note",
      "By",
    ],
  },
  {
    path: "/warehouses/export",
    stem: "warehouses",
    headers: ["Code", "Name", "Default", "Active"],
  },
  {
    path: "/payments/export",
    stem: "payments",
    headers: [
      "Received on",
      "Partner",
      "Mode",
      "Reference",
      "Amount",
      "Allocated",
      "Unallocated",
      "Short payment",
      "Allocations",
      "Remark",
      "Entered by",
      "Entered",
      "Voided",
      "Void reason",
    ],
  },
  {
    path: "/warranty-terms/export",
    stem: "warranty-terms",
    headers: ["Product category", "Months", "From", "To"],
  },
  {
    path: "/org-units/export",
    stem: "offices",
    headers: ["Name", "Level", "Parent", "Territory", "Open", "Closed", "Active people", "Created"],
  },
  {
    path: "/territories/export",
    stem: "territories",
    headers: ["Name", "Level", "Code", "Parent", "Created"],
  },
  {
    path: "/dealer-applications/export",
    stem: "dealer-applications",
    headers: ["Firm", "Contact", "Type", "Territory", "Status", "Deposit", "Created", "Submitted"],
  },
  {
    path: "/campaigns/export",
    stem: "campaigns",
    headers: [
      "Name",
      "Type",
      "Territory",
      "Start",
      "End",
      "Planned cost",
      "Actual cost",
      "Active",
      "Leads",
      "Won",
      "Sales value",
      "Description",
    ],
  },
  {
    path: "/schemes/export",
    stem: "schemes",
    headers: [
      "Code",
      "Name",
      "Type",
      "Metric",
      "Minimum",
      "Maximum",
      "Benefit",
      "Value",
      "Cap",
      "Period",
      "From",
      "To",
      "For",
      "Priority",
      "Stackable",
      "Active",
    ],
  },
  {
    path: "/scheme-entitlements/export",
    stem: "scheme-entitlements",
    headers: [
      "Scheme",
      "Partner",
      "Kind",
      "Value",
      "Cap",
      "Status",
      "Earned",
      "Expires",
      "From order",
      "Used on order",
    ],
  },
  {
    path: "/rewards/ledger/export",
    stem: "reward-points",
    headers: ["When", "Points", "Kind", "Reason", "Expires"],
  },
  {
    path: "/rewards/gift-redemptions/export",
    stem: "gift-redemptions",
    headers: [
      "Requested",
      "Holder",
      "Holder type",
      "Kind",
      "Gift",
      "Points",
      "Amount",
      "Status",
      "Decided",
      "Remark",
    ],
  },
  {
    path: "/reward-rules/export",
    stem: "reward-rules",
    headers: [
      "Code",
      "Name",
      "For",
      "Basis",
      "Points",
      "Per amount",
      "From",
      "To",
      "Expiry (days)",
      "Active",
    ],
  },
  { path: "/gifts/export", stem: "gifts", headers: ["Name", "Description", "Points", "Active"] },
  {
    path: "/subsidy-schemes/export",
    stem: "subsidy-schemes",
    headers: ["Code", "Name", "State", "Systems", "Ready", "Active", "Applications"],
  },
  { path: "/holidays/export", stem: "holidays", headers: ["Date", "Name"] },
  {
    path: "/seller-gstins/export",
    stem: "seller-gstins",
    headers: ["GSTIN", "Legal name", "State code", "Default", "Active", "LUTs"],
  },
  {
    path: "/ratings/export",
    stem: "ratings",
    headers: [
      "When",
      "About",
      "Score",
      "Comment",
      "Rated by",
      "Entered via",
      "Entered by",
      "Partner",
      "Lead",
      "Order",
      "Complaint",
      "Product",
    ],
  },
];

/** One sample row: "Sample" under the first heading, the rest blank. */
function sampleRow(headers: readonly string[]): readonly string[] {
  return headers.map((_, index) => (index === 0 ? "Sample" : ""));
}

export const listExportHandlers = LIST_EXPORTS.map(({ path, stem, headers }) =>
  http.get(buildApiUrl(path), ({ request }) =>
    mockWorkbook(stem, headers, [sampleRow(headers)], request),
  ),
);
