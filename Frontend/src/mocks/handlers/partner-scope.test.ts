import { afterEach, describe, expect, it } from "vitest";

import { getComplaint } from "@/features/complaints/api/complaints.api";
import { getDashboardOverview } from "@/features/dashboard/api/dashboard.api";
import { getLead, getLeadStats, listLeads } from "@/features/leads/api/leads.api";
import type { LeadListParams } from "@/features/leads/api/leads.schemas";
import { getOrder } from "@/features/orders/api/orders.api";
import { isApiError } from "@/lib/api/errors";
import { PARTNER_ROLES } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";

function reset(): void {
  resetMockDb();
  writeMockRole("state_manager");
}

const LIST: LeadListParams = {
  cursor: null,
  pageSize: 100,
  sort: "createdAt",
  order: "desc",
  q: "",
  stage: [],
  source: null,
  type: null,
  areas: [],
  campaign: null,
};

describe("[APP-008] What a partner user reads in the mock", () => {
  afterEach(reset);

  it("gives each partner user only the leads their dealership holds", async () => {
    reset();
    const all = mockDb.leads.filter((lead) => lead.stage !== "merged").length;
    expect((await getLeadStats()).total).toBe(all);

    for (const role of PARTNER_ROLES) {
      writeMockRole(role);
      const partnerId = mockMeFor(role).data.partner?.id;
      const page = await listLeads(LIST);
      expect((await getLeadStats()).total).toBe(page.items.length);
      expect(page.items.length).toBeGreaterThan(0);
      expect(page.items.length).toBeLessThan(all);
      for (const lead of page.items) {
        expect(mockDb.leads.find((item) => item.id === lead.id)?.assigned_partner?.id).toBe(
          partnerId,
        );
      }
    }
  });

  it("answers 404 for another dealership's lead, and sums the dashboard over the dealer's own", async () => {
    reset();
    const staffPipeline = (await getDashboardOverview()).kpis.pipelineValue;
    const other = mockDb.leads.find(
      (lead) =>
        lead.stage !== "merged" &&
        lead.assigned_partner?.id !== mockMeFor("dealer").data.partner?.id,
    );
    if (other === undefined) throw new Error("Mock leads changed.");

    writeMockRole("dealer");
    const refused = await getLead(other.id).then(
      () => null,
      (error: unknown) => (isApiError(error) ? error.status : null),
    );
    expect(refused).toBe(404);
    expect((await getDashboardOverview()).kpis.pipelineValue).not.toEqual(staffPipeline);
  });

  it("answers 404 for another dealership's order or complaint", async () => {
    reset();
    const mine = mockMeFor("dealer").data.partner?.id;
    const order = mockDb.orders.find((item) => item.partner?.id !== mine);
    const complaint = mockDb.complaints.find((item) => item.partner?.id !== mine);
    if (order === undefined || complaint === undefined) throw new Error("Mock data changed.");
    const statusOf = (call: Promise<unknown>): Promise<number | null> =>
      call.then(
        () => null,
        (error: unknown) => (isApiError(error) ? (error.status ?? null) : null),
      );

    expect(await statusOf(getOrder(order.id))).toBeNull();
    writeMockRole("dealer");
    expect(await statusOf(getOrder(order.id))).toBe(404);
    expect(await statusOf(getComplaint(complaint.id))).toBe(404);
  });
});
