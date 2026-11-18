import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  getApplication,
  listApplications,
  listDocumentTypes,
  recordStage,
  reopenApplication,
} from "@/features/subsidy/api/subsidy-applications.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ApplicationDetail } from "./application-detail";
import { SubsidyMasters } from "./subsidy-masters";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), notFound: vi.fn() }));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

function show(ui: React.JSX.Element, searchParams = ""): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      {ui}
      <Toaster />
    </>,
    { searchParams },
  );
  return user;
}

async function closedApplicationId(): Promise<string> {
  const page = await listApplications({
    status: "full_fp_received",
    stage: null,
    q: "",
    leadId: null,
    cursor: null,
  });
  const first = page.items[0];
  if (first === undefined) throw new Error("No closed application in the seed");
  return first.id;
}

describe("[SUBS-015] reopenApplication", () => {
  beforeEach(() => {
    signInAs("admin");
  });
  afterEach(reset);

  it("opens a closed file again; it stays open until a payment entry closes it", async () => {
    const id = await closedApplicationId();

    const reopened = await reopenApplication(id, {
      body: { reason: "FP date entered wrong" },
      idempotencyKey: "s-1",
    });
    expect(reopened.status).toBe("open");
    expect((await getApplication(id)).status).toBe("open");

    const closedAgain = await recordStage(id, {
      body: {
        stage_code: "payment_received",
        occurred_on: todayInIndia(),
        values: { farmer_share_received: todayInIndia() },
        remark: "Corrected the farmer share date",
      },
      idempotencyKey: "s-2",
    });
    expect(closedAgain.status).toBe("full_fp_received");
  });

  it("refuses an open file, a missing reason, and someone without subsidy.approve", async () => {
    const id = await closedApplicationId();
    await expect(
      reopenApplication(id, { body: { reason: " " }, idempotencyKey: "s-3" }),
    ).rejects.toMatchObject({ status: 422, details: { fields: { reason: expect.any(String) } } });

    await reopenApplication(id, { body: { reason: "Wrong date" }, idempotencyKey: "s-4" });
    await expect(
      reopenApplication(id, { body: { reason: "Again" }, idempotencyKey: "s-5" }),
    ).rejects.toMatchObject({ status: 409, code: "application_not_closed" });

    signInAs("employee");
    await expect(
      reopenApplication(id, { body: { reason: "Mine" }, idempotencyKey: "s-6" }),
    ).rejects.toMatchObject({ status: 403 });
  });

  it("reads the document checklist", async () => {
    const types = await listDocumentTypes();
    expect(types.length).toBeGreaterThan(0);
    expect(types[0]).toMatchObject({ code: expect.any(String), active: true });
  });
});

describe("[SUBS-015] Reopen on the application", () => {
  afterEach(reset);

  it("offers Reopen on a closed file to those who approve, and reopens it with a reason", async () => {
    signInAs("admin");
    const user = show(<ApplicationDetail applicationId={await closedApplicationId()} />);

    expect(await screen.findByText(/Reopen it to correct an entry/)).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Reopen" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/It closes again when the payment entries/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Reopen" }));
    expect(await within(dialog).findByText("Say why it is reopened.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Why reopen it"), "FP date entered wrong");
    await user.click(within(dialog).getByRole("button", { name: "Reopen" }));

    expect(
      await screen.findByText("Application reopened", { selector: "[data-title]" }),
    ).toBeVisible();
    expect(await screen.findByRole("button", { name: "Record stage" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reopen" })).not.toBeInTheDocument();
  });

  it("offers no Reopen to someone who can't approve subsidy files", async () => {
    signInAs("district_manager");
    show(<ApplicationDetail applicationId={await closedApplicationId()} />);

    expect(await screen.findByText(/Every payment received/)).toBeInTheDocument();
    expect(screen.queryByText(/Reopen it to correct an entry/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reopen" })).not.toBeInTheDocument();
  });

  it("says so when the dealer's commission is settled, and keeps the file closed", async () => {
    signInAs("admin");
    const user = show(<ApplicationDetail applicationId={await closedApplicationId()} />);
    server.use(
      http.post(buildApiUrl("/subsidy-applications/:applicationId/reopen"), () =>
        HttpResponse.json(
          { error: { code: "commission_settled", message: "The commission is settled." } },
          { status: 409 },
        ),
      ),
    );

    await user.click(await screen.findByRole("button", { name: "Reopen" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Why reopen it"), "Wrong amount");
    await user.click(within(dialog).getByRole("button", { name: "Reopen" }));

    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent("The dealer's commission is settled");
  });

  it("closes and refreshes when the file isn't closed any more", async () => {
    signInAs("admin");
    const user = show(<ApplicationDetail applicationId={await closedApplicationId()} />);
    server.use(
      http.post(buildApiUrl("/subsidy-applications/:applicationId/reopen"), () =>
        HttpResponse.json(
          { error: { code: "application_not_closed", message: "Only a closed one." } },
          { status: 409 },
        ),
      ),
    );

    await user.click(await screen.findByRole("button", { name: "Reopen" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Why reopen it"), "Wrong amount");
    await user.click(within(dialog).getByRole("button", { name: "Reopen" }));

    expect(
      await screen.findByText("This application isn't closed any more", {
        selector: "[data-title]",
      }),
    ).toBeVisible();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});

describe("[SUBS-007] The document checklist in the subsidy masters", () => {
  afterEach(reset);

  it("lists the checklist, and marks an item no longer asked for", async () => {
    signInAs("admin");
    server.use(
      http.get(buildApiUrl("/subsidy-document-types"), () =>
        HttpResponse.json({
          data: [
            {
              id: "d-1",
              code: "farmer_application_form_1",
              name: "Farmer Application (Form-1)",
              is_active: true,
            },
            { id: "d-2", code: "old_affidavit", name: "Old affidavit", is_active: false },
          ],
        }),
      ),
    );
    show(<SubsidyMasters />, "?table=documents");

    const list = await screen.findByRole("list", { name: "Document checklist" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText("Farmer Application (Form-1)")).toBeInTheDocument();
    expect(within(list).getByText("No longer asked for")).toBeInTheDocument();
    expect(screen.getByText("1 of 2 items still asked for")).toBeInTheDocument();
  });
});
