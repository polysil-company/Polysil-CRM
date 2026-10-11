import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ComplaintDetail } from "./complaint-detail";
import { ComplaintForm } from "./complaint-form";
import { ComplaintsList } from "./complaints-list";

const push = vi.fn();
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push, back: vi.fn() }),
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
  push.mockReset();
}

function seeded(status: string): string {
  const complaint = mockDb.complaints.find(
    (item) => item.status === status && item.check?.decision !== "return",
  );
  if (complaint === undefined) throw new Error(`No ${status} complaint`);
  return complaint.id;
}

function show(complaintId: string): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <ComplaintDetail complaintId={complaintId} />
      <Toaster />
    </>,
  );
  return user;
}

describe("[CMPL-001] ComplaintsList", () => {
  afterEach(reset);

  it("lists complaints newest first, with status, severity, late and the counts", async () => {
    signInAs("admin");
    renderWithProviders(<ComplaintsList />);

    const list = await screen.findByRole("list", { name: "Complaints" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(mockDb.complaints.length);
    expect(within(list).getAllByText("Late").length).toBeGreaterThan(0);
    expect(await screen.findByText(/\d+ waiting for a check · \d+ with QC/)).toBeInTheDocument();
  });

  it("filters by status in the URL", async () => {
    signInAs("admin");
    const user = userEvent.setup();
    const onUrlChange = vi.fn<(queryString: string) => void>();
    renderWithProviders(<ComplaintsList />, { onUrlChange });
    await screen.findByRole("list", { name: "Complaints" });

    await user.click(screen.getByRole("button", { name: "Status" }));
    await user.click(await screen.findByRole("checkbox", { name: "With QC" }));

    await waitFor(() => {
      expect(onUrlChange).toHaveBeenLastCalledWith(expect.stringContaining("status=under_qc"));
    });
    await waitFor(() => {
      const rows = within(screen.getByRole("list", { name: "Complaints" })).getAllByRole(
        "listitem",
      );
      expect(rows.every((row) => /With QC/.test(row.textContent))).toBe(true);
    });
  });

  it("shows a manager what waits on their check", async () => {
    signInAs("district_manager");
    renderWithProviders(<ComplaintsList />, { searchParams: "?view=mine" });

    const list = await screen.findByRole("list", { name: "Complaints" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows.every((row) => /Waiting for a check/.test(row.textContent))).toBe(true);
    expect(screen.getByText(/oldest first/)).toBeInTheDocument();
  });

  it("offers no queue and no new complaint to someone who can only look", async () => {
    signInAs("account_manager");
    renderWithProviders(<ComplaintsList />);

    await screen.findByRole("list", { name: "Complaints" });
    expect(screen.queryByRole("button", { name: "Waiting on me" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "New complaint" })).not.toBeInTheDocument();
  });
});

describe("[CMPL-003] Raise and submit", () => {
  afterEach(reset);

  it("explains every missing field, and refuses more defective than supplied", async () => {
    signInAs("employee");
    const user = userEvent.setup();
    renderWithProviders(<ComplaintForm complaint={null} />);

    await user.click(screen.getByRole("button", { name: "Save as draft" }));
    expect(await screen.findByText("Choose what kind of complaint it is.")).toBeInTheDocument();
    expect(screen.getByText("Say what went wrong.")).toBeInTheDocument();
    expect(screen.getByText("Enter a 10-digit Indian mobile number.")).toBeInTheDocument();
    expect(screen.getByText("Choose where the material is installed.")).toBeInTheDocument();
    expect(screen.getByText("Choose the product.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Supplied"), "10");
    await user.type(screen.getByLabelText("Defective"), "11");
    await user.click(screen.getByRole("button", { name: "Save as draft" }));
    expect(await screen.findByText("Not more than supplied.")).toBeInTheDocument();
  });

  it("submits a draft: it gets its number and waits for the check", async () => {
    signInAs("employee");
    const draft = mockDb.complaints.find(
      (item) => item.status === "draft" && item.dc_no !== null && item.check === null,
    );
    if (draft === undefined) throw new Error("No ready draft");
    const user = show(draft.id);

    await user.click(await screen.findByRole("button", { name: "Submit" }));

    expect(await screen.findByText("Submitted", { selector: "[data-title]" })).toBeVisible();
    expect(await screen.findByRole("heading", { name: /^Poly\/Comp\./ })).toBeInTheDocument();
  });

  it("says what is missing when a draft can't be submitted yet", async () => {
    signInAs("employee");
    const draft = mockDb.complaints.find((item) => item.status === "draft" && item.dc_no === null);
    if (draft === undefined) throw new Error("No draft without a challan");
    const user = show(draft.id);

    await user.click(await screen.findByRole("button", { name: "Submit" }));

    expect(
      await screen.findByText("Not ready to submit", { selector: "[data-title]" }),
    ).toBeVisible();
    expect(
      screen.getByText(/Add the challan number and the supply date first/),
    ).toBeInTheDocument();
  });

  it("shows a returned draft's reason", async () => {
    signInAs("employee");
    const returned = mockDb.complaints.find((item) => item.check?.decision === "return");
    if (returned === undefined) throw new Error("No returned draft");
    show(returned.id);

    expect(await screen.findByText(/^Returned to fix/)).toBeInTheDocument();
    expect(screen.getByText(/Add the supply date from the challan/)).toBeInTheDocument();
  });
});

describe("[CMPL-004] The manager's check", () => {
  afterEach(reset);

  it("needs a remark, then approves it to QC", async () => {
    signInAs("district_manager");
    const user = show(seeded("submitted"));

    await user.click(await screen.findByRole("button", { name: "Check" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Approve" }));
    expect(
      await within(dialog).findByText("Write a remark. Whoever raised it reads it."),
    ).toBeVisible();

    await user.type(within(dialog).getByLabelText("Remark"), "Genuine.");
    await user.click(within(dialog).getByRole("button", { name: "Approve" }));

    expect(
      await screen.findByText("Approved: sent to QC", { selector: "[data-title]" }),
    ).toBeVisible();
    expect(await screen.findAllByText("With QC")).not.toHaveLength(0);
  });

  it("returns it to fix", async () => {
    signInAs("district_manager");
    const user = show(seeded("submitted"));

    await user.click(await screen.findByRole("button", { name: "Check" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: "Return to fix" }));
    await user.type(within(dialog).getByLabelText("Remark"), "Add a photo.");
    await user.click(within(dialog).getByRole("button", { name: "Return" }));

    expect(
      await screen.findByText("Returned to whoever raised it", { selector: "[data-title]" }),
    ).toBeVisible();
  });

  it("closes and refreshes when someone checked it first", async () => {
    signInAs("district_manager");
    server.use(
      http.post(buildApiUrl("/complaints/:id/check"), () =>
        HttpResponse.json({ error: { code: "status_changed", message: "moved" } }, { status: 409 }),
      ),
    );
    const user = show(seeded("submitted"));
    await user.click(await screen.findByRole("button", { name: "Check" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Remark"), "ok");
    await user.click(within(dialog).getByRole("button", { name: "Approve" }));

    expect(
      await screen.findByText("This complaint moved on", { selector: "[data-title]" }),
    ).toBeVisible();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});

describe("[CMPL-005] The QC verdict", () => {
  afterEach(reset);

  it("rejects with what QC found, closing the complaint", async () => {
    signInAs("qa_manager");
    const user = show(seeded("under_qc"));

    await user.click(await screen.findByRole("button", { name: "Give the QC verdict" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: "Rejected: no defect" }));
    await user.type(within(dialog).getByLabelText("What QC found"), "Rodent damage.");
    await user.click(within(dialog).getByRole("button", { name: "Reject" }));

    expect(await screen.findByText("QC rejected", { selector: "[data-title]" })).toBeVisible();
    expect(
      await screen.findByText("Rejected: no defect", { selector: "span" }),
    ).toBeInTheDocument();
  });

  it("offers QC nothing on a complaint still waiting for the check", async () => {
    signInAs("qa_manager");
    show(seeded("submitted"));

    await screen.findByRole("heading", { level: 2 });
    expect(screen.queryByRole("button", { name: "Give the QC verdict" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check" })).not.toBeInTheDocument();
  });
});

describe("[CMPL-003] Cancel", () => {
  afterEach(reset);

  it("cancels with a reason, which then shows on the complaint", async () => {
    signInAs("employee");
    const user = show(seeded("submitted"));

    await user.click(await screen.findByRole("button", { name: "Cancel complaint" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Reason"), "Raised twice.");
    await user.click(within(dialog).getByRole("button", { name: "Cancel complaint" }));

    expect(
      await screen.findByText("Complaint cancelled", { selector: "[data-title]" }),
    ).toBeVisible();
    const notice = await screen.findByRole("note");
    expect(within(notice).getByText("Raised twice.")).toBeInTheDocument();
  });
});
