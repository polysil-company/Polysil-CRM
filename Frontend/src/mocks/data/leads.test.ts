import { describe, expect, it } from "vitest";

import { generateLeads } from "./leads";

const NOW = Date.parse("2026-09-14T10:00:00+05:30");

describe("[LEAD-001] mock lead data", () => {
  it("is deterministic for a seed", () => {
    const [first] = generateLeads(3, 7, NOW);
    const [again] = generateLeads(3, 7, NOW);

    expect(first).toEqual(again);
  });

  it("produces a believable funnel with closed and open leads", () => {
    const leads = generateLeads(137, 20_260_914, NOW);
    const statuses = new Set(leads.map((lead) => lead.status));

    expect(leads).toHaveLength(137);
    expect(statuses.has("won")).toBe(true);
    expect(statuses.has("lost")).toBe(true);
    expect(
      leads.filter((lead) => lead.status === "lost").every((lead) => lead.lostReason !== null),
    ).toBe(true);
    expect(
      leads.filter((lead) => lead.status === "won").every((lead) => lead.followUpAt === null),
    ).toBe(true);
  });

  it("uses unique ids and codes", () => {
    const leads = generateLeads(137, 20_260_914, NOW);

    expect(new Set(leads.map((lead) => lead.id)).size).toBe(leads.length);
    expect(new Set(leads.map((lead) => lead.code)).size).toBe(leads.length);
  });
});
