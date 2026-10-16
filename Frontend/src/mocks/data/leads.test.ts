import { describe, expect, it } from "vitest";

import { leadWireSchema } from "@/features/leads/api/leads.schemas";

import { generateLeads } from "./leads";
import { mockLookupCodes } from "./lookups";

const NOW = Date.parse("2026-09-14T10:00:00+05:30");

describe("[LEAD-001] mock lead data", () => {
  it("is deterministic for a seed", () => {
    const [first] = generateLeads(3, 7, NOW);
    const [again] = generateLeads(3, 7, NOW);

    expect(first).toEqual(again);
  });

  it("follows the backend's contract, newest first", () => {
    const leads = generateLeads(137, 20_260_914, NOW);

    expect(leads).toHaveLength(137);
    for (const lead of leads) {
      expect(leadWireSchema.safeParse(lead).success, lead.inquiry_no).toBe(true);
    }
    const created = leads.map((lead) => Date.parse(lead.created_at));
    expect(created).toEqual([...created].sort((a, b) => b - a));
  });

  it("produces a believable funnel: lost leads carry a reason, merged ones point at their survivor", () => {
    const leads = generateLeads(137, 20_260_914, NOW);
    const stages = new Set(leads.map((lead) => lead.stage));

    expect(stages.has("won")).toBe(true);
    expect(stages.has("lost")).toBe(true);
    expect(
      leads.filter((lead) => lead.stage === "lost").every((lead) => lead.lost_reason !== null),
    ).toBe(true);
    expect(
      leads.filter((lead) => lead.stage !== "lost").every((lead) => lead.lost_reason === null),
    ).toBe(true);
    expect(
      leads.filter((lead) => lead.merged_into !== null).every((lead) => lead.stage === "merged"),
    ).toBe(true);
  });

  it("uses the seeded lookup codes, money as decimal strings and E.164 mobiles", () => {
    const leads = generateLeads(137, 20_260_914, NOW);
    const sources = mockLookupCodes("lead-sources");
    const systems = mockLookupCodes("mis-systems");

    expect(leads.every((lead) => sources.includes(lead.source))).toBe(true);
    expect(leads.every((lead) => systems.includes(lead.mis_system))).toBe(true);
    expect(leads.every((lead) => /^\+91[6-9]\d{9}$/.test(lead.mobile))).toBe(true);
    const values = leads.flatMap((lead) =>
      lead.estimated_value === null ? [] : [lead.estimated_value],
    );
    expect(values.length).toBeGreaterThan(0);
    expect(values.every((value) => /^\d+\.\d{2}$/.test(value))).toBe(true);
  });

  it("flags leads that share a mobile number as pending duplicates, on both leads", () => {
    const leads = generateLeads(137, 20_260_914, NOW);
    const flagged = leads.filter((lead) => (lead.duplicates ?? []).length > 0);

    expect(flagged.length).toBeGreaterThan(0);
    for (const lead of flagged) {
      for (const link of lead.duplicates ?? []) {
        const other = leads.find((candidate) => candidate.id === link.lead_id);
        expect(other?.mobile).toBe(lead.mobile);
        expect(other?.duplicates?.some((back) => back.lead_id === lead.id)).toBe(true);
      }
    }
  });

  it("uses unique ids and inquiry numbers", () => {
    const leads = generateLeads(137, 20_260_914, NOW);

    expect(new Set(leads.map((lead) => lead.id)).size).toBe(leads.length);
    expect(new Set(leads.map((lead) => lead.inquiry_no)).size).toBe(leads.length);
  });
});
