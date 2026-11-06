import type { ReportName } from "@/features/reports/api/reports.schemas";

/** One way to group a report's rows; the first is the backend's default. */
interface GroupOption {
  readonly value: string;
  readonly label: string;
}

interface ReportEntry {
  readonly title: string;
  /** What it counts, in a sentence, for the home card and the report's header. */
  readonly description: string;
  /** Takes a from–to window (follow-ups is as of now). */
  readonly dates: boolean;
  readonly territory: boolean;
  /** Takes one person (`owner_id`). */
  readonly owner: boolean;
  /** FS-082 · Takes a team (`team_of`) and roles (`roles`). */
  readonly team: boolean;
  /** Its `group_by` (or `level`) choices, the default first; empty when it has none. */
  readonly groups: readonly GroupOption[];
  /** Its figures follow the company's setting for when an order counts as a sale. */
  readonly sales: boolean;
}

/**
 * RPT-002 · The reports in the order the home page shows them, with the filters each takes
 * (`api/routers/reports.py`). The titles and descriptions are the frontend's.
 */
export const REPORTS: Readonly<Record<ReportName, ReportEntry>> = {
  "lead-conversion": {
    title: "Lead conversion",
    description: "Leads created in the window, how far they got, and how many were won.",
    dates: true,
    territory: true,
    owner: true,
    team: true,
    groups: [
      { value: "source", label: "Source" },
      { value: "owner", label: "Person" },
      { value: "territory", label: "Territory" },
    ],
    sales: false,
  },
  "salesperson-performance": {
    title: "Salesperson performance",
    description: "Per person: leads created and won, quotations sent, orders, visits and tasks.",
    dates: true,
    territory: true,
    owner: true,
    team: true,
    groups: [],
    sales: true,
  },
  "lost-leads": {
    title: "Lost leads",
    description: "Leads lost in the window: why, how long it took, and where they dropped off.",
    dates: true,
    territory: true,
    owner: true,
    team: true,
    groups: [
      { value: "reason", label: "Reason" },
      { value: "owner", label: "Person" },
    ],
    sales: false,
  },
  "follow-ups": {
    title: "Follow-ups",
    description: "Open tasks per person as of now: due today, and overdue by how long.",
    dates: false,
    territory: false,
    owner: true,
    team: true,
    groups: [],
    sales: false,
  },
  "dealer-performance": {
    title: "Dealer performance",
    description:
      "Per dealer: orders and value in the window, value shipped, leads given, and what they owe.",
    dates: true,
    territory: true,
    owner: false,
    team: false,
    groups: [],
    sales: true,
  },
  "campaign-performance": {
    title: "Campaign performance",
    description: "Per campaign: its leads in the window, how far they got, its sales and its cost.",
    dates: true,
    territory: true,
    owner: true,
    team: true,
    groups: [],
    sales: true,
  },
  "territory-performance": {
    title: "Territory performance",
    description: "Per district or taluka: leads, wins, conversion, orders and their value.",
    dates: true,
    territory: true,
    owner: false,
    team: true,
    groups: [
      { value: "district", label: "District" },
      { value: "taluka", label: "Taluka" },
    ],
    sales: true,
  },
  complaints: {
    title: "Complaints",
    description:
      "Complaints first submitted in the window: resolved, within target, breaches, refunds.",
    dates: true,
    territory: true,
    owner: true,
    team: false,
    groups: [
      { value: "type", label: "Type" },
      { value: "status", label: "Status" },
      { value: "severity", label: "Severity" },
    ],
    sales: false,
  },
  "sales-forecast": {
    title: "Sales forecast",
    description:
      "What the open pipeline is likely to bring in, and roughly when, weighted by each stage's win rate.",
    dates: false,
    territory: true,
    owner: true,
    team: true,
    groups: [
      { value: "owner", label: "Person" },
      { value: "territory", label: "Territory" },
      { value: "source", label: "Source" },
    ],
    sales: false,
  },
  insights: {
    title: "Insights",
    description: "Plain sentences about the window against the same number of days before it.",
    dates: true,
    territory: true,
    owner: true,
    team: true,
    groups: [],
    sales: false,
  },
};

/** "Sales counted at: approval", as the handover words it (`when-a-sale-counts.md`). */
export function saleModeLabel(mode: string): string {
  return mode.replaceAll("_", " ");
}
