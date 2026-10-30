import { http, HttpResponse } from "msw";

import type {
  AssistantActionWire,
  AssistantRecordWire,
} from "@/features/assistant/api/assistant.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { MOCK_ASSISTANT_ACTIONS, type MockAssistantAction } from "@/mocks/data/assistant";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * BOT-001, BOT-002 · The assistant (`docs/api/assistant.md`). Actions the user may take, best
 * match first; from 3 characters, records by number, mobile or name, scoped like their lists. A
 * farmer never gets here: the portal fence answers 403 first.
 */

const STARTER_COUNT = 6;
const RECORD_CAP = 10;
const QUERY_MAX = 100;
// The backend's rule: no control characters in `q`.
const CONTROL = /[\u0000-\u001f\u007f]/;

function allowed(): MockAssistantAction[] {
  const role = readMockRole();
  const permissions = mockPermissionsFor(role);
  return MOCK_ASSISTANT_ACTIONS.filter(
    (entry) =>
      !(entry.staffOnly === true && isPartnerRole(role)) &&
      (entry.needs === null || can(permissions, entry.needs.module, entry.needs.action)),
  );
}

function wireOf(entry: MockAssistantAction): AssistantActionWire {
  return {
    key: entry.key,
    title: entry.title,
    hint: entry.hint,
    screen: entry.screen,
    module: entry.module,
  };
}

/** 3 when the title starts with the term, 2 when it holds it, 1 for the hint, 0 for none. */
function scoreOf(entry: MockAssistantAction, term: string): number {
  const words = term.split(/\s+/).filter((word) => word !== "");
  const title = entry.title.toLowerCase();
  const hint = entry.hint.toLowerCase();
  if (!words.every((word) => title.includes(word) || hint.includes(word))) return 0;
  if (title.startsWith(term)) return 3;
  return words.every((word) => title.includes(word)) ? 2 : 1;
}

function matchActions(term: string, limit: number): AssistantActionWire[] {
  const actions = allowed();
  if (term === "") return actions.slice(0, Math.min(STARTER_COUNT, limit)).map(wireOf);
  return actions
    .map((entry, index) => ({ entry, index, score: scoreOf(entry, term) }))
    .filter((row) => row.score > 0)
    .sort((left, right) => right.score - left.score || left.index - right.index)
    .slice(0, limit)
    .map((row) => wireOf(row.entry));
}

/** A number like `QT/2026-27/00123` matches its text, or its serial alone (`123`). */
function numberMatches(number: string | null, term: string): boolean {
  if (number === null) return false;
  const lower = number.toLowerCase();
  if (lower.includes(term)) return true;
  if (!/^\d+$/.test(term)) return false;
  const serial = /(\d+)$/.exec(number)?.[1];
  return serial !== undefined && Number(serial) === Number(term);
}

function matchRecords(term: string): AssistantRecordWire[] {
  const role = readMockRole();
  const permissions = mockPermissionsFor(role);
  const partnerId = isPartnerRole(role) ? (mockMeFor(role).data.partner?.id ?? null) : null;
  const ours = (partner: { id: string } | null | undefined): boolean =>
    partnerId === null || partner?.id === partnerId;
  const digits = term.replace(/\D/g, "");
  const byMobile = (mobile: string): boolean =>
    digits.length >= 4 && mobile.replace(/\D/g, "").includes(digits);
  const records: AssistantRecordWire[] = [];

  if (can(permissions, "leads", "view")) {
    const leads = mockDb.leads.filter(
      (lead) =>
        lead.stage !== "merged" &&
        ours(lead.assigned_partner) &&
        (lead.inquiry_no.toLowerCase().includes(term) ||
          lead.farmer_name.toLowerCase().includes(term) ||
          byMobile(lead.mobile)),
    );
    for (const lead of leads) {
      records.push({
        kind: "lead",
        id: lead.id,
        label: `${lead.inquiry_no} · ${lead.farmer_name}`,
        screen: "leads.detail",
      });
    }
    const customerIds = new Set(leads.map((lead) => lead.customer_id));
    for (const customer of mockDb.customers) {
      const seen = mockDb.leads.some(
        (lead) => lead.customer_id === customer.id && ours(lead.assigned_partner),
      );
      if (!seen) continue;
      if (
        customerIds.has(customer.id) ||
        customer.name.toLowerCase().includes(term) ||
        byMobile(customer.mobile)
      ) {
        records.push({
          kind: "customer",
          id: customer.id,
          label:
            customer.village === null ? customer.name : `${customer.name} · ${customer.village}`,
          screen: "customers.detail",
        });
      }
    }
  }
  if (can(permissions, "quotations", "view")) {
    for (const quotation of mockDb.quotations) {
      if (!ours(quotation.partner) || !numberMatches(quotation.quote_no, term)) continue;
      records.push({
        kind: "quotation",
        id: quotation.id,
        label: `${quotation.quote_no ?? "Draft"} · ${quotation.party.name}`,
        screen: "quotations.detail",
      });
    }
  }
  if (can(permissions, "sales_orders", "view")) {
    for (const order of mockDb.orders) {
      if (!ours(order.partner) || !numberMatches(order.order_no, term)) continue;
      records.push({
        kind: "sales_order",
        id: order.id,
        label: `${order.order_no ?? "Draft"} · ${order.party.name}`,
        screen: "orders.detail",
      });
    }
  }
  if (can(permissions, "complaints", "view")) {
    for (const complaint of mockDb.complaints) {
      if (!ours(complaint.partner) || !numberMatches(complaint.complaint_no, term)) continue;
      records.push({
        kind: "complaint",
        id: complaint.id,
        label: `${complaint.complaint_no ?? "Draft"} · ${complaint.contact_name}`,
        screen: "complaints.detail",
      });
    }
  }
  return records.slice(0, RECORD_CAP);
}

export const assistantHandlers = [
  http.get(buildApiUrl("/assistant/actions"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    return HttpResponse.json({ data: scenario === "empty" ? [] : allowed().map(wireOf) });
  }),

  http.get(buildApiUrl("/assistant"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const url = new URL(request.url);
    const q = url.searchParams.get("q") ?? "";
    const limitText = url.searchParams.get("limit");
    const limit = limitText === null ? 8 : Number(limitText);
    const fields: Record<string, string> = {};
    if (q.length > QUERY_MAX) fields.q = "At most 100 characters.";
    else if (CONTROL.test(q)) fields.q = "No control characters.";
    if (!Number.isInteger(limit) || limit < 1 || limit > 20) fields.limit = "1 to 20.";
    if (Object.keys(fields).length > 0) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
    }
    const term = q.trim().toLowerCase();
    if (scenario === "empty") return HttpResponse.json({ data: { actions: [], records: [] } });
    return HttpResponse.json({
      data: {
        actions: matchActions(term, limit),
        records: term.length >= 3 ? matchRecords(term) : [],
      },
    });
  }),
];
