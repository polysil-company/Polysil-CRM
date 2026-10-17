import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getMinutes } from "@/features/tasks/api/tasks.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { LeadTasks } from "./lead-tasks";
import { MinutesDetail } from "./minutes-detail";

const notFound = vi.fn();
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  notFound: () => {
    notFound();
  },
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
  notFound.mockClear();
}

function seededMinutes(): { id: string; leadId: string } {
  const minutes = mockDb.minutes[0];
  if (minutes?.lead == null) throw new Error("No seeded minutes on a lead");
  return { id: minutes.id, leadId: minutes.lead.id };
}

describe("[TASK-007] getMinutes", () => {
  afterEach(reset);

  it("reads one set of minutes with each action item as it stands now", async () => {
    signInAs("admin");
    const { id, leadId } = seededMinutes();

    const minutes = await getMinutes(id);

    expect(minutes.lead?.id).toBe(leadId);
    expect(minutes.actionItems.map((task) => task.status).sort()).toEqual(["done", "open"]);
  });

  it("answers 404 for minutes that don't exist", async () => {
    signInAs("admin");
    await expect(getMinutes("missing")).rejects.toMatchObject({ status: 404 });
  });
});

describe("[TASK-007] MinutesDetail", () => {
  afterEach(reset);

  it("shows the meeting, the lead it was about, and how many action items are done", async () => {
    signInAs("admin");
    const { id, leadId } = seededMinutes();
    renderWithProviders(<MinutesDetail minutesId={id} />);

    expect(await screen.findByRole("heading", { name: /^Meeting on / })).toBeInTheDocument();
    const lead = screen.getByRole("link", { name: /POL\// });
    expect(lead).toHaveAttribute("href", `/leads/${leadId}`);
    expect(screen.getByText("1 of 2 done")).toBeInTheDocument();
    const items = screen.getByRole("list", { name: "Action items" });
    expect(within(items).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/Walked the plot with the family/)).toBeInTheDocument();
  });

  it("is not found when the minutes are out of scope", async () => {
    signInAs("admin");
    renderWithProviders(<MinutesDetail minutesId="missing" />);

    await vi.waitFor(() => {
      expect(notFound).toHaveBeenCalled();
    });
  });

  it("is linked from an action item's task", async () => {
    signInAs("admin");
    const { id, leadId } = seededMinutes();
    renderWithProviders(<LeadTasks leadId={leadId} leadName="The farmer" merged={false} />);

    const links = await screen.findAllByRole("link", { name: "From meeting minutes" });
    expect(links[0]).toHaveAttribute("href", `/tasks/minutes/${id}`);
  });
});
