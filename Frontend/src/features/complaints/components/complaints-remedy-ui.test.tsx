import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { decideApprovalStep } from "@/features/approvals/api/approvals.api";
import { ApprovalsInbox } from "@/features/approvals/components/approvals-inbox";
import { chooseRemedy } from "@/features/complaints/api/complaints.api";
import { buildApiUrl } from "@/lib/api/url";
import { ROLES, type Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ComplaintDetail } from "./complaint-detail";
import { ComplaintTargets } from "./complaint-targets";
import { RelatedComplaints } from "./related-complaints";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

function seeded(status: string): string {
  const complaint = mockDb.complaints.find((item) => item.status === status);
  if (complaint === undefined) throw new Error(`No ${status} complaint`);
  return complaint.id;
}

function show(ui: React.JSX.Element): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      {ui}
      <Toaster />
    </>,
  );
  return user;
}

describe("[CMPL-007] The remedy", () => {
  afterEach(reset);

  it("asks QC for an amount, then sends the refund for approval and shows its steps", async () => {
    signInAs("qa_manager");
    const user = show(<ComplaintDetail complaintId={seeded("qc_approved")} />);

    await user.click(await screen.findByRole("button", { name: "Choose the remedy" }));
    const dialog = await screen.findByRole("dialog", { name: "Choose the remedy" });
    await user.click(within(dialog).getByRole("button", { name: "Send for approval" }));
    expect(await within(dialog).findByText(/Enter an amount above 0/)).toBeInTheDocument();
    expect(within(dialog).getByText("Say why this remedy.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Amount (₹)"), "1500");
    await user.type(within(dialog).getByLabelText("Why this remedy"), "Burst within a month");
    await user.click(within(dialog).getByRole("button", { name: "Send for approval" }));

    expect(await screen.findByText("Refund sent for approval")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("list", { name: "Approval steps, in order" })).toBeInTheDocument();
    expect(screen.getAllByText("₹1,500.00").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Withdraw" })).toBeInTheDocument();
  });

  it("closes with no remedy, which says what happens before choosing", async () => {
    signInAs("qa_manager");
    const user = show(<ComplaintDetail complaintId={seeded("qc_approved")} />);

    await user.click(await screen.findByRole("button", { name: "Choose the remedy" }));
    const dialog = await screen.findByRole("dialog", { name: "Choose the remedy" });
    await user.click(within(dialog).getByRole("radio", { name: "No action" }));
    expect(within(dialog).getByText(/The complaint closes now/)).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Amount (₹)")).not.toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Why this remedy"), "Goodwill only");
    await user.click(within(dialog).getByRole("button", { name: "Close with no remedy" }));

    expect(await screen.findByText("Closed with no remedy")).toBeInTheDocument();
  });

  it("offers no remedy to anyone but QC", async () => {
    signInAs("district_manager");
    show(<ComplaintDetail complaintId={seeded("qc_approved")} />);

    await screen.findByRole("heading", { name: "Targets" });
    expect(screen.queryByRole("button", { name: "Choose the remedy" })).not.toBeInTheDocument();
  });

  it("puts the refund in Accounts' inbox, which needs the payment reference to approve", async () => {
    writeMockRole("qa_manager");
    const id = seeded("qc_approved");
    const chosen = await chooseRemedy(id, {
      body: { kind: "refund", amount: "500", payee_name: "Kiritbhai Shah", remark: "Leak" },
      idempotencyKey: "remedy-1",
    });
    // The managers approve first, from their own inboxes.
    for (const step of chosen.remedy?.refund?.approval?.steps.slice(0, -1) ?? []) {
      const role = ROLES.find((known) => known === step.role);
      if (role === undefined) throw new Error(`Not a role: ${step.role}`);
      writeMockRole(role);
      await decideApprovalStep(step.id, {
        body: { decision: "approve", remark: null },
        idempotencyKey: `approve-${step.id}`,
      });
    }

    signInAs("account_manager");
    const user = show(<ApprovalsInbox />);
    const row = await screen.findByRole("listitem", { name: /^Complaint refund:/ });
    expect(within(row).getByRole("link", { name: "Open the complaint" })).toHaveAttribute(
      "href",
      `/complaints/${id}`,
    );
    await user.click(within(row).getByRole("button", { name: /^Approve/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Approve" }));
    expect(
      await within(dialog).findByText("Enter the payment reference: the UTR or cheque number."),
    ).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Payment reference"), "UTR 0042");
    await user.click(within(dialog).getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Approved", { selector: "[data-title]" })).toBeInTheDocument();
    expect(mockDb.complaints.find((item) => item.id === id)).toMatchObject({
      status: "closed",
      remedy: { refund: { payment_reference: "UTR 0042" } },
    });
  });
});

describe("[CMPL-006] Files", () => {
  afterEach(reset);

  it("shows the files with their kind, and removes one", async () => {
    signInAs("admin");
    const complaint = mockDb.complaints.find((item) => item.status === "draft");
    if (complaint === undefined) throw new Error("No draft");
    complaint.attachments.push({
      id: "a-1",
      kind: "challan",
      filename: "challan-4471.pdf",
      content_type: "application/pdf",
      size_bytes: 300 * 1024,
      preview: true,
      uploaded_by: null,
      uploaded_at: new Date().toISOString(),
    });
    const user = show(<ComplaintDetail complaintId={complaint.id} />);

    const files = await screen.findByRole("list", { name: "Files" });
    expect(within(files).getByText("challan-4471.pdf")).toBeInTheDocument();
    expect(within(files).getByText("Challan")).toBeInTheDocument();
    await user.click(
      within(files).getByRole("button", { name: "Remove Challan: challan-4471.pdf" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Remove this file?" });
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));

    expect(
      await screen.findByText("No files yet. Add photos of the defect first."),
    ).toBeInTheDocument();
  });

  it("refuses a file that is too large before sending it", async () => {
    signInAs("admin");
    const user = show(<ComplaintDetail complaintId={seeded("draft")} />);
    await screen.findByRole("button", { name: "Add files" });
    // The picker is hidden behind "Add files"; the test hands it the file directly.
    const input = screen.getByTestId("complaint-file-input");
    const big = new File(["x"], "huge.jpg", { type: "image/jpeg" });
    Object.defineProperty(big, "size", { value: 11 * 1024 * 1024 });
    await user.upload(input, big);

    expect(await screen.findByText("One file wasn't added")).toBeInTheDocument();
    expect(screen.getByText("huge.jpg: over 10 MB")).toBeInTheDocument();
  });

  it("says when files can't be stored, and offers no upload", async () => {
    signInAs("admin");
    server.use(
      http.get(buildApiUrl("/complaints/stats"), () =>
        HttpResponse.json({
          data: { by_status: {}, breached: 0, no_target: 0, storage_available: false },
        }),
      ),
    );
    show(<ComplaintDetail complaintId={seeded("draft")} />);

    expect(await screen.findByText(/File storage isn't set up yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add files" })).not.toBeInTheDocument();
  });
});

describe("[CMPL-008] ComplaintTargets", () => {
  afterEach(reset);

  it("shows each severity's target in force, in working hours", async () => {
    signInAs("employee");
    show(<ComplaintTargets />);

    const high = await screen.findByRole("list", { name: "High severity targets" });
    expect(within(high).getByText("4 working hours")).toBeInTheDocument();
    expect(within(high).getByText("18 working hours (2 days)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Set a new target/ })).not.toBeInTheDocument();
  });

  it("sets a new target from today, refusing a resolution quicker than the response", async () => {
    signInAs("admin");
    const user = show(<ComplaintTargets />);

    await user.click(
      await screen.findByRole("button", { name: "Set a new target for low severity" }),
    );
    const dialog = await screen.findByRole("dialog");
    const response = within(dialog).getByLabelText("First response (hours)");
    const resolution = within(dialog).getByLabelText("Resolution (hours)");
    await user.clear(response);
    await user.type(response, "10");
    await user.clear(resolution);
    await user.type(resolution, "5");
    await user.click(within(dialog).getByRole("button", { name: "Set target" }));
    expect(
      await within(dialog).findByText("Resolution can't be quicker than the first response."),
    ).toBeInTheDocument();

    await user.clear(resolution);
    await user.type(resolution, "36");
    await user.click(within(dialog).getByRole("button", { name: "Set target" }));

    expect(await screen.findByText("Target set")).toBeInTheDocument();
    const low = await screen.findByRole("list", { name: "Low severity targets" });
    expect(within(low).getByText("10 working hours")).toBeInTheDocument();
    // The one in force before ends today, so it moves to the past.
    expect(within(low).queryByText("9 working hours")).not.toBeInTheDocument();
  });
});

describe("[CMPL-001] RelatedComplaints", () => {
  afterEach(reset);

  it("lists a lead's complaints and raises one about it", async () => {
    signInAs("admin");
    const complaint = mockDb.complaints.find((item) => item.lead !== null);
    if (complaint?.lead == null) throw new Error("No complaint about a lead");
    show(<RelatedComplaints about={{ leadId: complaint.lead.id }} />);

    const list = await screen.findByRole("list", { name: "Complaints" });
    expect(within(list).getAllByRole("listitem").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Raise a complaint" })).toHaveAttribute(
      "href",
      `/complaints/new?lead=${complaint.lead.id}`,
    );
  });

  it("shows nothing to someone who may not see complaints", async () => {
    signInAs("dispatch_manager");
    const { container } = renderWithProviders(<RelatedComplaints about={{ orderId: "o-1" }} />);
    await waitFor(() => {
      expect(container).toBeEmptyDOMElement();
    });
  });
});
