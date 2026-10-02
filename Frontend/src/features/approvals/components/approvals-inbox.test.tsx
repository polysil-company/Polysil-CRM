import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import type { QueuePageWire } from "@/features/approvals/api/approvals.schemas";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ApprovalsInbox } from "./approvals-inbox";

/** Unit tests have no access token, so the session is served directly for one role. */
function signInAs(role: Role): void {
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(searchParams = ""): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <ApprovalsInbox />
      <Toaster />
    </>,
    { searchParams },
  );
  return user;
}

async function rows(): Promise<HTMLElement[]> {
  const list = await screen.findByRole("list", { name: /Waiting for your decision/ });
  return within(list).getAllByRole("listitem");
}

describe("[APPR-001] ApprovalsInbox", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("shows quotation discounts and sales orders waiting on the manager, with the count", async () => {
    signInAs("state_manager");
    show();

    const items = await rows();
    expect(
      screen.getByText(`${String(items.length)} waiting for your decision, oldest first.`),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Quotation discount").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Sales order").length).toBeGreaterThan(0);
    expect(screen.getByText("No District Manager to decide")).toBeInTheDocument();
    expect(screen.getAllByText(/discount asked$/).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Open the quotation" }).length).toBeGreaterThan(0);
  });

  it("needs a reason to reject, then removes the request from the inbox", async () => {
    signInAs("state_manager");
    const user = show();
    const [first] = await rows();
    if (first === undefined) {
      throw new Error("The inbox is empty");
    }
    const before = (await rows()).length;

    await user.click(within(first).getByRole("button", { name: /^Reject/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Reject" }));
    expect(
      await within(dialog).findByText("Say why. The person who asked reads it."),
    ).toBeVisible();
    await user.type(within(dialog).getByLabelText(/^Reason/), "Offer 8% instead");
    await user.click(within(dialog).getByRole("button", { name: "Reject" }));

    expect(await screen.findByText("Rejected", { selector: "[data-title]" })).toBeInTheDocument();
    await waitFor(async () => {
      expect(await rows()).toHaveLength(before - 1);
    });
  });

  it("approves without a remark", async () => {
    signInAs("state_manager");
    const user = show();
    const [first] = await rows();
    if (first === undefined) {
      throw new Error("The inbox is empty");
    }

    await user.click(within(first).getByRole("button", { name: /^Approve/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Approve" }));

    expect(await screen.findByText("Approved", { selector: "[data-title]" })).toBeInTheDocument();
    expect(mockDb.approvalSteps.some((step) => step.decision === "approve")).toBe(true);
  });

  it("closes the dialog and refreshes when someone decided the step first", async () => {
    signInAs("state_manager");
    server.use(
      http.post(buildApiUrl("/approvals/steps/:stepId/decision"), () =>
        HttpResponse.json(
          { error: { code: "step_already_decided", message: "decided" } },
          { status: 409 },
        ),
      ),
    );
    const user = show();
    const [first] = await rows();
    if (first === undefined) {
      throw new Error("The inbox is empty");
    }

    await user.click(within(first).getByRole("button", { name: /^Approve/ }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve" }),
    );

    expect(await screen.findByText("Already decided")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("includes lower steps from the URL, and offers no decisions without the permission", async () => {
    signInAs("employee");
    show("?below=true");

    await rows();
    expect(screen.getByRole("checkbox", { name: "Include steps below me" })).toBeChecked();
    expect(screen.queryByRole("button", { name: /^Approve/ })).not.toBeInTheDocument();
  });

  it("says when nothing is waiting", async () => {
    signInAs("state_manager");
    server.use(
      http.get(buildApiUrl("/approvals/pending"), () => {
        const body: QueuePageWire = {
          data: [],
          meta: { limit: 25, next_cursor: null, total: 0, total_capped: false },
        };
        return HttpResponse.json(body);
      }),
    );
    show();

    expect(await screen.findByText("Nothing waits on you")).toBeInTheDocument();
    expect(screen.getByText("Nothing is waiting for you.")).toBeInTheDocument();
  });
});
