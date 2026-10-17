import { http, HttpResponse } from "msw";

import type { LeadWire } from "@/features/leads/api/leads.schemas";
import type { OrderWire } from "@/features/orders/api/orders.schemas";
import {
  REPORT_MAX_DAYS,
  REPORT_NAMES,
  REPORT_ROW_CAP,
  type Lead360Wire,
  type ReportName,
  type ReportWire,
} from "@/features/reports/api/reports.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can, type ModuleCode } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { calendarDayOf, shiftCalendarDay, todayInIndia } from "@/lib/format";
import { mockLookupRows } from "@/mocks/data/lookups";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockTerritoryLineage } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse, mockWorkbook } from "./shared";
import { mockApplications } from "./subsidy-applications";

/**
 * RPT-002, RPT-003 · The reports and a lead's 360° view for the mock backend
 * (`api/services/reports.py`). Figures are counted from the mock's own leads, orders, tasks and
 * complaints, so the filters change them. Where the mock has no data, it says so:
 *  - Payments, visits and campaign costs belong to modules the mock grants no one but Admin
 *    (`payments`, `tracking`, `campaigns` aren't in its permission list), so they're null for
 *    everyone else, as the backend sends a figure the user may not see.
 *  - Leads carry no stage-change dates here: a lead is won or lost on its last activity, and
 *    where a lost lead dropped off is drawn from its id.
 *  - Complaints carry no first-submitted date here, so the complaints report ignores the window.
 *  - Campaigns aren't built yet (item 27): three seeded ones stand in.
 *  - The sale setting is read as "approval", the backend's default.
 */

const DAY_MS = 24 * 60 * 60 * 1000;
const SALE_TYPES: ReadonlySet<string> = new Set([
  "commercial",
  "industrial",
  "export",
  "subsidised",
]);
const STAFF_ONLY: ReadonlySet<ReportName> = new Set([
  "salesperson-performance",
  "follow-ups",
  "territory-performance",
  "campaign-performance",
]);
const FUNNEL = ["new", "contacted", "qualified", "quoted", "negotiation", "won"] as const;
const DROP_OFF = ["contacted", "qualified", "quoted"] as const;

function hash(text: string): number {
  let value = 0;
  for (const char of text) value = (value * 31 + char.charCodeAt(0)) % 100_003;
  return value;
}

function money(value: number): string {
  return value.toFixed(2);
}

function pct(part: number, whole: number): string {
  return whole === 0 ? "0.0" : ((part / whole) * 100).toFixed(1);
}

function isReportName(value: string): value is ReportName {
  return REPORT_NAMES.some((name) => name === value);
}

// ── who may see what ─────────────────────────────────────────────────────────────

function has(module: ModuleCode): boolean {
  return can(mockPermissionsFor(readMockRole()), module);
}

/** Payments, visits and campaign costs: modules the mock gives only Admin. */
function seesUnlisted(): boolean {
  return readMockRole() === "admin";
}

function refusal(report: ReportName, ...modules: ModuleCode[]): Response | null {
  if (!has("reports")) return errorResponse(403, "insufficient_permission", "No reports.view.");
  if (STAFF_ONLY.has(report) && isPartnerRole(readMockRole())) {
    return errorResponse(403, "insufficient_permission", "This report is for staff.");
  }
  const missing = modules.filter((module) => !has(module));
  return missing.length === 0
    ? null
    : errorResponse(403, "insufficient_permission", `This report needs ${missing.join(", ")}.`);
}

// ── filters ──────────────────────────────────────────────────────────────────────

interface Filters {
  readonly from: string;
  readonly to: string;
  readonly territories: readonly string[];
  readonly owner: string | null;
}

function filtersOf(params: URLSearchParams): Filters | Response {
  const to = params.get("to") ?? todayInIndia();
  const from = params.get("from") ?? shiftCalendarDay(to, -29);
  if (from > to)
    return errorResponse(422, "validation_error", "Bad window.", { from: "from is after to" });
  const days = (Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS + 1;
  if (days > REPORT_MAX_DAYS) {
    return errorResponse(422, "validation_error", "Bad window.", { from: "at most a year" });
  }
  const territories = (params.get("territory_id") ?? "")
    .split(",")
    .map((id) => id.trim())
    .filter((id) => id !== "");
  return { from, to, territories, owner: params.get("owner_id") };
}

function inWindow(filters: Filters, at: string | null): boolean {
  if (at === null) return false;
  const day = calendarDayOf(at);
  return day >= filters.from && day <= filters.to;
}

function inArea(filters: Filters, territoryId: string): boolean {
  if (filters.territories.length === 0) return true;
  return mockTerritoryLineage(territoryId).some((territory) =>
    filters.territories.includes(territory.id),
  );
}

function filtersOut(filters: Filters): ReportWire<"lead-conversion">["filters"] {
  return {
    from: filters.from,
    to: filters.to,
    territory_id: filters.territories.length === 0 ? null : [...filters.territories],
    owner_id: filters.owner,
    sale_counted_at: "approval",
  };
}

/** The leads a report counts: not merged, in the areas and for the person asked. */
function leads(filters: Filters): LeadWire[] {
  return mockDb.leads.filter(
    (lead) =>
      lead.stage !== "merged" &&
      inArea(filters, lead.territory.id) &&
      (filters.owner === null || lead.owner?.id === filters.owner),
  );
}

/** Orders that are sales, counted on the day they were approved (the default setting). */
function sales(filters: Filters, ownerFilter = true): OrderWire[] {
  return mockDb.orders.filter(
    (order) =>
      SALE_TYPES.has(order.order_type) &&
      order.status !== "draft" &&
      order.status !== "cancelled" &&
      inWindow(filters, order.approved_at) &&
      inArea(filters, order.territory.id) &&
      (!ownerFilter || filters.owner === null || order.owner?.id === filters.owner),
  );
}

/** A lost or dormant lead's last stage before it dropped: drawn from its id here. */
function droppedFrom(lead: LeadWire): (typeof DROP_OFF)[number] {
  return DROP_OFF[hash(lead.id) % DROP_OFF.length] ?? "contacted";
}

function reached(lead: LeadWire, stage: (typeof DROP_OFF)[number]): boolean {
  if (lead.stage === "won") return true;
  const target = FUNNEL.indexOf(stage);
  if (lead.stage === "lost" || lead.stage === "dormant") {
    return DROP_OFF.indexOf(droppedFrom(lead)) >= DROP_OFF.indexOf(stage);
  }
  const index = FUNNEL.findIndex((item) => item === lead.stage);
  return index >= target;
}

function capped<Row>(rows: Row[]): { rows: Row[]; truncated: boolean } {
  return { rows: rows.slice(0, REPORT_ROW_CAP), truncated: rows.length > REPORT_ROW_CAP };
}

// ── the reports ──────────────────────────────────────────────────────────────────

function leadConversion(filters: Filters, groupBy: string): ReportWire<"lead-conversion"> {
  const sources = new Map(mockLookupRows("lead-sources").map((row) => [row.code, row]));
  const groups = new Map<string, { id: string | null; label: string; leads: LeadWire[] }>();
  for (const lead of leads(filters).filter((item) => inWindow(filters, item.created_at))) {
    const key =
      groupBy === "owner"
        ? { id: lead.owner?.id ?? null, label: lead.owner?.full_name ?? "Unassigned" }
        : groupBy === "territory"
          ? { id: lead.territory.id, label: lead.territory.name }
          : {
              id: sources.get(lead.source)?.id ?? lead.source,
              label: sources.get(lead.source)?.name ?? lead.source,
            };
    const group = groups.get(key.id ?? "") ?? { ...key, leads: [] };
    group.leads.push(lead);
    groups.set(key.id ?? "", group);
  }
  const rows = [...groups.values()]
    .map((group) => {
      const won = group.leads.filter((lead) => lead.stage === "won").length;
      const lost = group.leads.filter((lead) => lead.stage === "lost").length;
      return {
        key: { id: group.id, label: group.label },
        leads: group.leads.length,
        contacted: group.leads.filter((lead) => reached(lead, "contacted")).length,
        qualified: group.leads.filter((lead) => reached(lead, "qualified")).length,
        quoted: group.leads.filter((lead) => reached(lead, "quoted")).length,
        won,
        lost,
        open: group.leads.length - won - lost,
        conversion_pct: pct(won, group.leads.length),
      };
    })
    .sort((left, right) => right.leads - left.leads);
  const total = rows.reduce((sum, row) => sum + row.leads, 0);
  const won = rows.reduce((sum, row) => sum + row.won, 0);
  return {
    ...capped(rows),
    totals: { leads: total, won, conversion_pct: pct(won, total) },
    filters: filtersOut(filters),
  };
}

function salespersonPerformance(filters: Filters): ReportWire<"salesperson-performance"> {
  const people = new Map<string, { name: string; created: number; won: number }>();
  const person = (
    id: string | null,
    name: string,
  ): { name: string; created: number; won: number } => {
    const entry = people.get(id ?? "") ?? { name, created: 0, won: 0 };
    people.set(id ?? "", entry);
    return entry;
  };
  for (const lead of leads(filters)) {
    if (inWindow(filters, lead.created_at)) {
      person(lead.owner?.id ?? null, lead.owner?.full_name ?? "Unassigned").created += 1;
    }
    if (lead.stage === "won" && inWindow(filters, lead.last_activity_at)) {
      person(lead.owner?.id ?? null, lead.owner?.full_name ?? "Unassigned").won += 1;
    }
  }
  const orders = sales(filters);
  const rows = [...people.entries()]
    .map(([id, entry]) => {
      const mine = orders.filter((order) => (order.owner?.id ?? "") === id);
      const tasks = mockDb.tasks.filter((task) => (task.assigned_to?.id ?? "") === id);
      return {
        user: { id: id === "" ? null : id, full_name: entry.name },
        leads_created: entry.created,
        leads_won: entry.won,
        quotations_sent: has("quotations")
          ? mockDb.quotations.filter(
              (quotation) =>
                (quotation.owner?.id ?? "") === id && inWindow(filters, quotation.sent_at),
            ).length
          : null,
        orders: has("sales_orders") ? mine.length : null,
        order_value: has("sales_orders")
          ? money(mine.reduce((sum, order) => sum + Number(order.totals.total), 0))
          : null,
        visits: seesUnlisted() ? hash(id) % 12 : null,
        tasks_done: has("tasks")
          ? tasks.filter((task) => task.status === "done" && inWindow(filters, task.completed_at))
              .length
          : null,
        tasks_overdue: has("tasks")
          ? tasks.filter((task) => task.status === "open" && Date.parse(task.due_at) < Date.now())
              .length
          : null,
      };
    })
    .sort((left, right) => right.leads_created - left.leads_created);
  return {
    ...capped(rows),
    totals: {
      leads_created: rows.reduce((sum, row) => sum + row.leads_created, 0),
      leads_won: rows.reduce((sum, row) => sum + row.leads_won, 0),
    },
    filters: filtersOut(filters),
  };
}

function lostLeads(filters: Filters, groupBy: string): ReportWire<"lost-leads"> {
  const groups = new Map<string, { id: string | null; label: string; leads: LeadWire[] }>();
  for (const lead of leads(filters).filter(
    (item) => item.stage === "lost" && inWindow(filters, item.last_activity_at),
  )) {
    const key =
      groupBy === "owner"
        ? { id: lead.owner?.id ?? null, label: lead.owner?.full_name ?? "Unassigned" }
        : { id: lead.lost_reason?.id ?? null, label: lead.lost_reason?.name ?? "Unassigned" };
    const group = groups.get(key.id ?? "") ?? { ...key, leads: [] };
    group.leads.push(lead);
    groups.set(key.id ?? "", group);
  }
  const total = [...groups.values()].reduce((sum, group) => sum + group.leads.length, 0);
  const rows = [...groups.values()]
    .map((group) => {
      const byStage: Record<string, number> = {};
      let days = 0;
      for (const lead of group.leads) {
        const stage = droppedFrom(lead);
        byStage[stage] = (byStage[stage] ?? 0) + 1;
        days += (Date.parse(lead.last_activity_at) - Date.parse(lead.created_at)) / DAY_MS;
      }
      return {
        key: { id: group.id, label: group.label },
        count: group.leads.length,
        share_pct: pct(group.leads.length, total),
        avg_days_to_loss: (days / group.leads.length).toFixed(1),
        by_stage: byStage,
      };
    })
    .sort((left, right) => right.count - left.count);
  return { ...capped(rows), totals: { lost: total }, filters: filtersOut(filters) };
}

function followUps(owner: string | null): ReportWire<"follow-ups"> {
  const today = todayInIndia();
  const people = new Map<
    string,
    { name: string; buckets: [number, number, number, number, number]; oldest: string | null }
  >();
  for (const task of mockDb.tasks) {
    if (task.status !== "open" || task.assigned_to === null) continue;
    if (owner !== null && task.assigned_to.id !== owner) continue;
    const due = calendarDayOf(task.due_at);
    if (due > today) continue;
    const late = Math.round(
      (Date.parse(`${today}T00:00:00Z`) - Date.parse(`${due}T00:00:00Z`)) / DAY_MS,
    );
    const bucket = late === 0 ? 0 : late <= 2 ? 1 : late <= 7 ? 2 : late <= 30 ? 3 : 4;
    const entry = people.get(task.assigned_to.id) ?? {
      name: task.assigned_to.full_name,
      buckets: [0, 0, 0, 0, 0],
      oldest: null,
    };
    entry.buckets[bucket] += 1;
    if (entry.oldest === null || task.due_at < entry.oldest) entry.oldest = task.due_at;
    people.set(task.assigned_to.id, entry);
  }
  const rows = [...people.entries()]
    .map(([id, entry]) => ({
      user: { id, full_name: entry.name },
      due_today: entry.buckets[0],
      overdue_1_2: entry.buckets[1],
      overdue_3_7: entry.buckets[2],
      overdue_8_30: entry.buckets[3],
      overdue_31_plus: entry.buckets[4],
      oldest_due_at: entry.oldest,
    }))
    .sort((left, right) => (left.oldest_due_at ?? "").localeCompare(right.oldest_due_at ?? ""));
  const sum = (pick: (row: (typeof rows)[number]) => number): number =>
    rows.reduce((total, row) => total + pick(row), 0);
  return {
    ...capped(rows),
    totals: {
      due_today: sum((row) => row.due_today),
      overdue_1_2: sum((row) => row.overdue_1_2),
      overdue_3_7: sum((row) => row.overdue_3_7),
      overdue_8_30: sum((row) => row.overdue_8_30),
      overdue_31_plus: sum((row) => row.overdue_31_plus),
    },
    filters: { as_of: new Date().toISOString(), owner_id: owner },
  };
}

function dealerPerformance(filters: Filters): ReportWire<"dealer-performance"> {
  const dealers = new Map<string, { name: string; orders: OrderWire[] }>();
  for (const order of sales(filters, false)) {
    if (order.partner === null) continue;
    const entry = dealers.get(order.partner.id) ?? { name: order.partner.name ?? "", orders: [] };
    entry.orders.push(order);
    dealers.set(order.partner.id, entry);
  }
  const rows = [...dealers.entries()]
    .map(([id, entry]) => {
      const value = entry.orders.reduce((sum, order) => sum + Number(order.totals.total), 0);
      const shipped = entry.orders.reduce(
        (sum, order) =>
          sum +
          (order.status === "dispatched" || order.status === "closed_short"
            ? Number(order.totals.total)
            : order.status === "partially_dispatched"
              ? Number(order.totals.total) / 2
              : 0),
        0,
      );
      const received = Math.round((value * (40 + (hash(id) % 60))) / 100);
      return {
        partner: { id, name: entry.name },
        orders: entry.orders.length,
        order_value: money(value),
        dispatched_value: money(shipped),
        leads_assigned: has("leads")
          ? mockDb.leads.filter(
              (lead) => lead.assigned_partner?.id === id && inWindow(filters, lead.created_at),
            ).length
          : null,
        received: seesUnlisted() ? money(received) : null,
        balance: seesUnlisted() ? money(value - received) : null,
        complaints: has("complaints")
          ? mockDb.complaints.filter((complaint) => complaint.partner?.id === id).length
          : null,
      };
    })
    .sort((left, right) => Number(right.order_value) - Number(left.order_value));
  return {
    ...capped(rows),
    totals: {
      orders: rows.reduce((sum, row) => sum + row.orders, 0),
      order_value: money(rows.reduce((sum, row) => sum + Number(row.order_value), 0)),
    },
    filters: filtersOut(filters),
  };
}

const MOCK_CAMPAIGNS = [
  {
    name: "Kharif drip drive",
    type: "field_demo",
    start: -40,
    end: -10,
    leads: 34,
    won: 6,
    cost: 85000,
  },
  {
    name: "Rajkot agri fair",
    type: "agri_fair",
    start: -12,
    end: -10,
    leads: 21,
    won: 3,
    cost: 120000,
  },
  {
    name: "WhatsApp subsidy reminder",
    type: "whatsapp",
    start: -5,
    end: null,
    leads: 48,
    won: 2,
    cost: 6000,
  },
] as const;

function campaignPerformance(filters: Filters): ReportWire<"campaign-performance"> {
  const today = todayInIndia();
  const rows = MOCK_CAMPAIGNS.map((campaign, index) => {
    const lost = Math.round(campaign.leads / 4);
    const salesValue = campaign.won * 92000;
    return {
      campaign: {
        id: `campaign-${String(index + 1)}`,
        name: campaign.name,
        type: campaign.type,
        start_date: shiftCalendarDay(today, campaign.start),
        end_date: campaign.end === null ? null : shiftCalendarDay(today, campaign.end),
        is_active: campaign.end === null,
      },
      leads: campaign.leads,
      qualified: Math.round(campaign.leads / 2),
      won: campaign.won,
      lost,
      open: campaign.leads - campaign.won - lost,
      conversion_pct: pct(campaign.won, campaign.leads),
      sales_count: has("sales_orders") ? campaign.won : null,
      sales_value: has("sales_orders") ? money(salesValue) : null,
      cost_planned: seesUnlisted() ? money(campaign.cost) : null,
      cost_actual: null,
      cost: seesUnlisted() ? money(campaign.cost) : null,
      cost_per_lead: seesUnlisted() ? money(campaign.cost / campaign.leads) : null,
      cost_per_won: seesUnlisted() && campaign.won > 0 ? money(campaign.cost / campaign.won) : null,
    };
  });
  return {
    rows,
    truncated: false,
    totals: {
      leads: rows.reduce((sum, row) => sum + row.leads, 0),
      won: rows.reduce((sum, row) => sum + row.won, 0),
      sales_value: has("sales_orders")
        ? money(rows.reduce((sum, row) => sum + Number(row.sales_value ?? 0), 0))
        : null,
      cost: seesUnlisted()
        ? money(rows.reduce((sum, row) => sum + Number(row.cost ?? 0), 0))
        : null,
    },
    filters: filtersOut(filters),
  };
}

function territoryPerformance(
  filters: Filters,
  level: string,
): ReportWire<"territory-performance"> {
  const at = (territoryId: string): { id: string | null; name: string } => {
    const found = mockTerritoryLineage(territoryId).find((territory) => territory.level === level);
    return found === undefined ? { id: null, name: "Above this level" } : found;
  };
  const groups = new Map<
    string,
    { id: string | null; name: string; leads: number; won: number; orders: number; value: number }
  >();
  const group = (
    territoryId: string,
  ): { leads: number; won: number; orders: number; value: number } => {
    const place = at(territoryId);
    const entry = groups.get(place.id ?? "") ?? {
      id: place.id,
      name: place.name,
      leads: 0,
      won: 0,
      orders: 0,
      value: 0,
    };
    groups.set(place.id ?? "", entry);
    return entry;
  };
  for (const lead of leads({ ...filters, owner: null })) {
    if (!inWindow(filters, lead.created_at)) continue;
    const entry = group(lead.territory.id);
    entry.leads += 1;
    if (lead.stage === "won") entry.won += 1;
  }
  for (const order of sales(filters, false)) {
    const entry = group(order.territory.id);
    entry.orders += 1;
    entry.value += Number(order.totals.total);
  }
  const rows = [...groups.values()]
    .map((entry) => ({
      territory: { id: entry.id, name: entry.name },
      leads: entry.leads,
      won: entry.won,
      conversion_pct: pct(entry.won, entry.leads),
      orders: has("sales_orders") ? entry.orders : null,
      order_value: has("sales_orders") ? money(entry.value) : null,
    }))
    .sort((left, right) => right.leads - left.leads);
  return {
    ...capped(rows),
    totals: {
      leads: rows.reduce((sum, row) => sum + row.leads, 0),
      won: rows.reduce((sum, row) => sum + row.won, 0),
    },
    filters: filtersOut(filters),
  };
}

function complaintsReport(filters: Filters, groupBy: string): ReportWire<"complaints"> {
  const counted = mockDb.complaints.filter(
    (complaint) =>
      complaint.status !== "draft" &&
      complaint.status !== "cancelled" &&
      complaint.sla !== null &&
      inArea(filters, complaint.territory.id) &&
      (filters.owner === null || complaint.owner?.id === filters.owner),
  );
  const groups = new Map<string, { label: string; items: typeof counted }>();
  for (const complaint of counted) {
    const key =
      groupBy === "status"
        ? { id: complaint.status, label: complaint.status }
        : groupBy === "severity"
          ? { id: complaint.severity, label: complaint.severity }
          : { id: complaint.complaint_type.id, label: complaint.complaint_type.name };
    const entry = groups.get(key.id) ?? { label: key.label, items: [] };
    entry.items.push(complaint);
    groups.set(key.id, entry);
  }
  const rows = [...groups.entries()]
    .map(([id, entry]) => {
      const resolved = entry.items.filter((item) => item.sla?.resolved_at != null);
      const inTime = resolved.filter(
        (item) =>
          item.sla?.resolved_at != null &&
          item.sla.resolution_due_at != null &&
          item.sla.resolved_at <= item.sla.resolution_due_at,
      );
      return {
        key: { id, label: entry.label },
        count: entry.items.length,
        resolved: resolved.length,
        resolved_within_sla_pct: pct(inTime.length, resolved.length),
        response_breaches: entry.items.filter((item) => item.sla?.response_breached === true)
          .length,
      };
    })
    .sort((left, right) => right.count - left.count);
  const refunds = counted.filter(
    (complaint) =>
      complaint.remedy?.kind === "refund" &&
      complaint.remedy.status === "completed" &&
      complaint.remedy.refund !== null,
  );
  return {
    rows,
    truncated: false,
    totals: {
      count: rows.reduce((sum, row) => sum + row.count, 0),
      resolved: rows.reduce((sum, row) => sum + row.resolved, 0),
      refunds: {
        count: refunds.length,
        amount: money(
          refunds.reduce(
            (sum, complaint) => sum + Number(complaint.remedy?.refund?.amount ?? 0),
            0,
          ),
        ),
      },
    },
    filters: filtersOut(filters),
  };
}

const GROUPS: Partial<Readonly<Record<ReportName, readonly string[]>>> = {
  "lead-conversion": ["source", "owner", "territory"],
  "lost-leads": ["reason", "owner"],
  complaints: ["type", "status", "severity"],
  "territory-performance": ["district", "taluka"],
};

/** The report's data, a refusal, or a 422. */
function run(name: ReportName, params: URLSearchParams): Response | { rows: readonly object[] } {
  const groups = GROUPS[name];
  const param = name === "territory-performance" ? "level" : "group_by";
  const groupBy = params.get(param) ?? groups?.[0] ?? "";
  if (groups !== undefined && !groups.includes(groupBy)) {
    return errorResponse(422, "validation_error", "Bad grouping.", { [param]: groups.join(", ") });
  }
  if (name === "follow-ups") return refusal(name, "tasks") ?? followUps(params.get("owner_id"));
  const filters = filtersOf(params);
  if (filters instanceof Response) return filters;
  switch (name) {
    case "lead-conversion":
      return refusal(name, "leads") ?? leadConversion(filters, groupBy);
    case "salesperson-performance":
      return refusal(name, "leads") ?? salespersonPerformance(filters);
    case "lost-leads":
      return refusal(name, "leads") ?? lostLeads(filters, groupBy);
    case "dealer-performance":
      return refusal(name, "sales_orders", "partners") ?? dealerPerformance(filters);
    case "campaign-performance":
      return refusal(name, "leads") ?? campaignPerformance(filters);
    case "territory-performance":
      return refusal(name, "leads") ?? territoryPerformance(filters, groupBy);
    case "complaints":
      return refusal(name, "complaints") ?? complaintsReport(filters, groupBy);
  }
}

/** The stand-in workbook: each row's top-level figures under their keys. */
function workbookOf(name: ReportName, rows: readonly object[]): Response {
  const first = rows[0];
  const headers = first === undefined ? [] : Object.keys(first);
  return mockWorkbook(
    `report-${name}`,
    headers,
    rows.map((row) =>
      Object.values(row).map((value: unknown) =>
        value === null ? "" : typeof value === "object" ? JSON.stringify(value) : String(value),
      ),
    ),
  );
}

// ── the 360° lead view ───────────────────────────────────────────────────────────

function lead360(lead: LeadWire): Lead360Wire {
  const orders = mockDb.orders.filter(
    (order) =>
      order.lead?.id === lead.id &&
      order.status !== "draft" &&
      order.status !== "cancelled" &&
      order.approved_at !== null,
  );
  const value = orders.reduce((sum, order) => sum + Number(order.totals.total), 0);
  const application = has("subsidy")
    ? mockApplications().find((item) => item.lead.id === lead.id)
    : undefined;
  return {
    lead: {
      id: lead.id,
      inquiry_no: lead.inquiry_no,
      farmer_name: lead.farmer_name,
      mobile: lead.mobile,
      stage: lead.stage,
    },
    related_leads: mockDb.leads
      .filter(
        (item) => item.mobile === lead.mobile && item.id !== lead.id && item.stage !== "merged",
      )
      .slice(0, 20)
      .map((item) => ({
        id: item.id,
        inquiry_no: item.inquiry_no,
        stage: item.stage,
        relation: "same_mobile",
      })),
    summary: {
      quotations: has("quotations")
        ? new Set(
            mockDb.quotations
              .filter((quotation) => quotation.lead?.id === lead.id)
              .map((quotation) => quotation.quote_no ?? quotation.id),
          ).size
        : null,
      orders: has("sales_orders") ? orders.length : null,
      order_value: has("sales_orders") ? money(value) : null,
      received: seesUnlisted() ? money(Math.round(value * 0.6)) : null,
      complaints: has("complaints")
        ? mockDb.complaints.filter((complaint) => complaint.lead?.id === lead.id).length
        : null,
      visits: seesUnlisted() ? hash(lead.id) % 5 : null,
      open_tasks: has("tasks")
        ? mockDb.tasks.filter((task) => task.lead?.id === lead.id && task.status === "open").length
        : null,
      subsidy_stage: application?.current_stage.seq ?? null,
    },
  };
}

export const reportHandlers = [
  http.get(buildApiUrl("/reports/:name"), async ({ request, params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const name = String(params.name);
    if (!isReportName(name)) return errorResponse(404, "not_found", "No such report.");
    const query = new URL(request.url).searchParams;
    const answer = run(name, query);
    if (answer instanceof Response) return answer;
    if (query.get("format") === "xlsx") return workbookOf(name, answer.rows);
    return HttpResponse.json({ data: answer });
  }),

  http.get(buildApiUrl("/leads/:leadId/360"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!has("leads") || !has("reports")) {
      return errorResponse(403, "insufficient_permission", "Needs leads and reports.");
    }
    const lead = mockDb.leads.find((item) => item.id === String(params.leadId));
    if (lead === undefined) return errorResponse(404, "not_found", "No such lead.");
    return HttpResponse.json({ data: lead360(lead) });
  }),
];
