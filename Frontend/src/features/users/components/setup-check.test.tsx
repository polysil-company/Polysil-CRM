import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { getSetupCheck, patchUser } from "@/features/users/api/users.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { SetupCheckCard } from "./setup-check-card";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

describe("[ADMN-009] The setup check (FS-082)", () => {
  afterEach(reset);

  it("lists every check, and who to fix, for an administrator only", async () => {
    signInAs("admin");
    const report = await getSetupCheck();
    expect(report.checks.map((check) => check.code)).toEqual([
      "staff_without_area",
      "staff_without_territories",
      "staff_skipping_a_level",
      "unplaced_staff",
      "partners_without_area",
    ]);
    const skipping = report.checks.find((check) => check.code === "staff_skipping_a_level");
    expect(skipping?.count).toBeGreaterThan(0);
    expect(skipping?.kind).toBe("person");
    expect(report.ok).toBe(false);

    signInAs("employee");
    await expect(getSetupCheck()).rejects.toMatchObject({ status: 403 });
  });

  it("shows the checks to fix on the dashboard, each person linked to their page", async () => {
    signInAs("admin");
    renderWithProviders(<SetupCheckCard />);

    const list = await screen.findByRole("list", { name: "Setup to fix" });
    const check = within(list).getByRole("listitem", {
      name: "Staff with no manager one level above them",
    });
    const people = within(check).getByRole("list", { name: /^Who to fix/ });
    const first = within(people).getAllByRole("link")[0];
    expect(first?.getAttribute("href")).toMatch(/^\/users\//);
    expect(
      screen.getByText("Their approvals and escalations jump straight to someone two levels up."),
    ).toBeInTheDocument();
  });

  it("says so in a line when nothing needs fixing", async () => {
    signInAs("admin");
    server.use(
      http.get(buildApiUrl("/users/setup-check"), () =>
        HttpResponse.json({ data: { ok: true, checks: [] } }),
      ),
    );
    renderWithProviders(<SetupCheckCard />);

    expect(await screen.findByRole("status")).toHaveTextContent("Setup: nothing to fix.");
  });

  it("shows nothing to someone who may not change people, or only part of the company", async () => {
    signInAs("employee");
    const { container } = renderWithProviders(<SetupCheckCard />);
    expect(container).toBeEmptyDOMElement();

    reset();
    signInAs("admin");
    server.use(
      http.get(buildApiUrl("/users/setup-check"), () =>
        HttpResponse.json(
          { error: { code: "insufficient_permission", message: "Global scope only." } },
          { status: 403 },
        ),
      ),
    );
    renderWithProviders(<SetupCheckCard />);
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(screen.queryByText("Setup to fix")).not.toBeInTheDocument();
  });
});

describe("[ADMN-009] An office that covers no area (FS-082)", () => {
  afterEach(reset);

  it("refuses a Field Officer in an office with no area, on the office", async () => {
    signInAs("admin");
    const officer = mockDb.users.find(
      (user) => user.is_active && user.role?.code === "field_officer",
    );
    const template = mockDb.offices[0];
    if (officer === undefined || template === undefined) throw new Error("No seeds.");
    mockDb.offices.push({
      ...template,
      id: "00000000-0000-4000-8000-0000000000aa",
      name: "Head Office",
      territory: null,
    });

    await expect(
      patchUser({
        userId: officer.id,
        body: { org_unit_id: "00000000-0000-4000-8000-0000000000aa" },
        idempotencyKey: "o-1",
      }),
    ).rejects.toMatchObject({
      status: 422,
      code: "office_has_no_area",
      details: { fields: { org_unit_id: expect.stringContaining("covers an area") } },
    });
  });
});
