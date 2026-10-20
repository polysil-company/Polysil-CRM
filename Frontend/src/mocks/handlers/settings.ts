import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { SettingWire } from "@/features/settings/api/settings.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ROLES } from "@/mocks/data/users";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * ADMN-007 · Company settings for the mock backend (FS-036): staff read them; those who may
 * edit masters change them, each value checked against its kind, and the answer is the full
 * list. The keys, values and descriptions are the backend's seeds (`app_setting`, migrations
 * 041 to 060).
 */

const SEEDED_AT = "2026-10-01T04:30:00.000Z";

function choice(key: string, value: string, allowed: string[], description: string): SettingWire {
  return {
    key,
    kind: "choice",
    value,
    allowed,
    min: null,
    max: null,
    description,
    updated_at: SEEDED_AT,
  };
}

function int(
  key: string,
  value: number,
  min: number,
  max: number,
  description: string,
): SettingWire {
  return { key, kind: "int", value, allowed: null, min, max, description, updated_at: SEEDED_AT };
}

function roles(key: string, value: string[], description: string): SettingWire {
  return {
    key,
    kind: "roles",
    value,
    allowed: null,
    min: null,
    max: null,
    description,
    updated_at: SEEDED_AT,
  };
}

function bands(key: string, value: number[], description: string): SettingWire {
  return {
    key,
    kind: "bands",
    value,
    allowed: null,
    min: null,
    max: null,
    description,
    updated_at: SEEDED_AT,
  };
}

/** The mock's settings, seeded on first read; other handlers read their values through it. */
export function mockSettings(): SettingWire[] {
  if (mockDb.settings !== null) return mockDb.settings;
  mockDb.settings = [
    choice(
      "order_amend_reapproval",
      "always",
      ["always", "value_rises"],
      "An amended order goes through the managers again always, or only when its total rises (Accounts and Dispatch always confirm).",
    ),
    int(
      "complaint_reopen_days",
      30,
      1,
      365,
      "Days after a complaint closes, or QC rejects it, during which it may be reopened.",
    ),
    roles(
      "complaint_reopen_roles",
      ["qc_manager", "support"],
      "Roles that may reopen a complaint. The person who raised it may also reopen a closed one.",
    ),
    choice(
      "complaint_reopen_clock",
      "restart",
      ["restart", "continue"],
      "On reopening, count the response and resolution targets again from now, or keep the original dates.",
    ),
    int("complaint_reopen_max", 2, 1, 10, "How many times one complaint may be reopened."),
    choice(
      "tasks_for_dealers",
      "off",
      ["off", "on"],
      "Managers may assign tasks to the users of dealers they can see; the dealer completes them.",
    ),
    choice(
      "export_tax_treatment",
      "lut",
      ["lut", "igst"],
      "Exports zero-rated under a LUT (no IGST, the LUT number printed), or charged IGST at each line's rate.",
    ),
    choice(
      "sample_pricing",
      "free",
      ["free", "charged"],
      "Sample orders are free (every line 100 % off, no GST), or priced like a commercial order.",
    ),
    int(
      "sample_max_value",
      50000,
      1,
      10000000,
      "The largest sample order, in rupees of list value before any discount.",
    ),
    choice(
      "sale_counted_at",
      "approval",
      ["submission", "approval", "dispatch", "payment"],
      "When an order counts as a sale in the reports and targets: when it is submitted, approved, fully dispatched or paid in full. Changing it restates past periods.",
    ),
    choice(
      "dealer_credit_check",
      "warn",
      ["off", "warn", "block"],
      "On submitting a dealer's order: ignore its credit limit, warn the approvers, or refuse the order.",
    ),
    choice(
      "complaint_escalation",
      "bell",
      ["off", "bell"],
      "When a complaint misses its response or resolution target: do nothing, or ring the bell for its owner and the managers handling it.",
    ),
    int(
      "dealer_rating_window_days",
      365,
      30,
      1095,
      "The dealer rating counts orders submitted in this many days, up to today.",
    ),
    bands(
      "dealer_rating_payment_days",
      [7, 15, 30, 60],
      "Days from order to full payment: at or under the first scores 5, the second 4, the third 3, the fourth 2; over the fourth, 1.",
    ),
    bands(
      "dealer_rating_order_value",
      [100000, 500000, 1000000, 2500000],
      "Rupees ordered before GST: at or over the fourth scores 5, the third 4, the second 3, the first 2; under the first, 1.",
    ),
    choice(
      "consumer_portal",
      "off",
      ["off", "on"],
      "Farmers sign in with a WhatsApp code and see their own enquiries, quotations, orders and complaints. On, every customer number can be sent a code.",
    ),
    int(
      "portal_otp_hourly_cap",
      100,
      0,
      10000,
      "Most sign-in codes sent to customers in one hour, across all numbers. 0 sends none. Dealers' codes are not counted.",
    ),
    roles(
      "replacement_approval_roles",
      ["state_manager", "regional_manager", "md_ceo"],
      "Who approves a replacement order, in order, before the Dispatch Manager. Each must be a manager who approves orders.",
    ),
  ];
  return mockDb.settings;
}

const patchSchema = z.object({
  values: z.record(
    z.string(),
    z.union([z.string(), z.number(), z.array(z.string()), z.array(z.number())]),
  ),
});

/** Why a value doesn't fit its setting, or null when it does. */
function problemOf(setting: SettingWire, value: unknown): string | null {
  switch (setting.kind) {
    case "choice":
      return typeof value === "string" && (setting.allowed ?? []).includes(value)
        ? null
        : `one of ${(setting.allowed ?? []).join(", ")}`;
    case "int":
      return typeof value === "number" &&
        Number.isInteger(value) &&
        value >= (setting.min ?? Number.MIN_SAFE_INTEGER) &&
        value <= (setting.max ?? Number.MAX_SAFE_INTEGER)
        ? null
        : `a whole number from ${String(setting.min)} to ${String(setting.max)}`;
    case "roles":
      return Array.isArray(value) &&
        value.every((code) => MOCK_ROLES.some((role) => role.code === code))
        ? null
        : "role codes";
    case "bands":
      return Array.isArray(value) &&
        value.length === 4 &&
        value.every((item, index) => {
          const previous: unknown = index === 0 ? -1 : value[index - 1];
          return (
            typeof item === "number" &&
            Number.isInteger(item) &&
            item >= 0 &&
            typeof previous === "number" &&
            item > previous
          );
        })
        ? null
        : "four whole numbers, rising";
  }
}

export const settingsHandlers = [
  http.get(buildApiUrl("/settings"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) {
      return errorResponse(403, "insufficient_permission", "Settings are for staff.");
    }
    return HttpResponse.json({ data: mockSettings() });
  }),

  http.patch(buildApiUrl("/settings"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (request.headers.get("idempotency-key") === null) {
      return errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.");
    }
    if (!can(mockPermissionsFor(readMockRole()), "masters", "edit")) {
      return errorResponse(403, "insufficient_permission", "You may not change settings.");
    }
    const parsed = patchSchema.safeParse(await request.json());
    if (!parsed.success || Object.keys(parsed.data.values).length === 0) {
      return errorResponse(422, "validation_error", "Send at least one setting.", {
        values: "at least one",
      });
    }
    const fields: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed.data.values)) {
      const setting = mockSettings().find((item) => item.key === key);
      if (setting === undefined) {
        fields[key] = "unknown setting";
        continue;
      }
      const problem = problemOf(setting, value);
      if (problem !== null) fields[key] = problem;
    }
    if (Object.keys(fields).length > 0) {
      return errorResponse(422, "validation_error", "Some settings need correcting.", fields);
    }
    const now = new Date().toISOString();
    for (const [key, value] of Object.entries(parsed.data.values)) {
      const setting = mockSettings().find((item) => item.key === key);
      if (setting !== undefined) {
        setting.value = value;
        setting.updated_at = now;
      }
    }
    return HttpResponse.json({ data: mockSettings() });
  }),
];
