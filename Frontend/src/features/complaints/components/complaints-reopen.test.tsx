import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { getComplaint, reopenComplaint } from "@/features/complaints/api/complaints.api";
import { complaintHistoryEntry, timesText } from "@/features/complaints/lib/complaint-labels";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ComplaintDetail } from "./complaint-detail";

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

describe("[CMPL-010] reopenComplaint", () => {
  afterEach(reset);

  it("lets the raiser reopen a closed complaint: a new round, counted, with the reason", async () => {
    signInAs("employee");
    const id = seeded("closed");
    expect((await getComplaint(id)).can.reopen).toBe(true);

    const reopened = await reopenComplaint(id, {
      body: { reason: "The same emitters failed again" },
      idempotencyKey: "r-1",
    });

    expect(reopened).toMatchObject({
      status: "submitted",
      reopenCount: 1,
      reopenReason: "The same emitters failed again",
      closedAt: null,
      check: null,
    });
    expect(reopened.reopenedAt).not.toBeNull();
    expect(reopened.can.reopen).toBe(false);
  });

  it("needs a reason", async () => {
    await expect(
      reopenComplaint(seeded("closed"), { body: { reason: "  " }, idempotencyKey: "r-2" }),
    ).rejects.toMatchObject({
      status: 422,
      code: "remark_required",
      details: { fields: { reason: expect.any(String) } },
    });
  });

  it("keeps a rejected complaint to the allowed roles", async () => {
    const id = seeded("qc_rejected");
    expect((await getComplaint(id)).can.reopen).toBe(false);
    await expect(
      reopenComplaint(id, { body: { reason: "Farmer disputes it" }, idempotencyKey: "r-3" }),
    ).rejects.toMatchObject({ status: 403 });

    signInAs("qa_manager");
    expect((await getComplaint(id)).can.reopen).toBe(true);
    await expect(
      reopenComplaint(id, { body: { reason: "Farmer disputes it" }, idempotencyKey: "r-4" }),
    ).resolves.toMatchObject({ status: "submitted", reopenCount: 1 });
  });

  it("refuses once it was reopened as often as allowed", async () => {
    const id = seeded("closed");
    mockDb.complaints = mockDb.complaints.map((item) =>
      item.id === id ? { ...item, reopen_count: 2 } : item,
    );

    expect((await getComplaint(id)).can.reopen).toBe(false);
    await expect(
      reopenComplaint(id, { body: { reason: "Again" }, idempotencyKey: "r-5" }),
    ).rejects.toMatchObject({ status: 422, code: "reopen_window_closed" });
  });

  it("refuses a complaint that is not closed or rejected as moved on", async () => {
    await expect(
      reopenComplaint(seeded("submitted"), { body: { reason: "Again" }, idempotencyKey: "r-6" }),
    ).rejects.toMatchObject({ status: 409, code: "status_changed" });
  });

  it("hides the reason from a dealer", async () => {
    const id = seeded("closed");
    await reopenComplaint(id, { body: { reason: "Internal: repeat site" }, idempotencyKey: "r-7" });

    // A partner user reads only their own dealership's complaints (APP-008).
    const complaint = mockDb.complaints.find((item) => item.id === id);
    const mine = mockMeFor("dealer").data.partner;
    if (complaint !== undefined && mine !== null && mine !== undefined) {
      complaint.partner = { id: mine.id, name: mine.name ?? "Dealer" };
    }
    signInAs("dealer");
    const seen = await getComplaint(id);
    expect(seen.reopenCount).toBe(1);
    expect(seen.reopenReason).toBeNull();
  });
});

describe("[CMPL-010] Reopen on the complaint", () => {
  afterEach(reset);

  it("reopens with a reason, then says how often and why, and the history shows it", async () => {
    signInAs("employee");
    const user = show(seeded("closed"));

    await user.click(await screen.findByRole("button", { name: "Reopen" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Reopen" }));
    expect(await within(dialog).findByText("Say why it is reopened.")).toBeInTheDocument();

    await user.type(
      within(dialog).getByLabelText("Why reopen it"),
      "The same emitters failed again",
    );
    await user.click(within(dialog).getByRole("button", { name: "Reopen" }));

    expect(
      await screen.findByText("Complaint reopened", { selector: "[data-title]" }),
    ).toBeVisible();
    const notice = await screen.findByRole("note");
    expect(within(notice).getByText("Reopened once")).toBeInTheDocument();
    expect(within(notice).getByText(/The same emitters failed again/)).toBeInTheDocument();
    expect(await screen.findByText("Reopened")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reopen" })).not.toBeInTheDocument();
  });

  it("offers no Reopen on a rejected complaint to someone outside the allowed roles", async () => {
    signInAs("admin");
    show(seeded("qc_rejected"));

    expect(await screen.findByRole("heading", { level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reopen" })).not.toBeInTheDocument();
  });

  it("closes and refreshes when the time to reopen has passed meanwhile", async () => {
    signInAs("employee");
    const user = show(seeded("closed"));
    server.use(
      http.post(buildApiUrl("/complaints/:complaintId/reopen"), () =>
        HttpResponse.json(
          {
            error: {
              code: "reopen_window_closed",
              message: "The time to reopen this complaint has passed.",
            },
          },
          { status: 422 },
        ),
      ),
    );

    await user.click(await screen.findByRole("button", { name: "Reopen" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Why reopen it"), "Again");
    await user.click(within(dialog).getByRole("button", { name: "Reopen" }));

    expect(
      await screen.findByText("It can no longer be reopened", { selector: "[data-title]" }),
    ).toBeVisible();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});

describe("[CMPL-010] reopen words", () => {
  it("counts the times", () => {
    expect([1, 2, 3].map(timesText)).toEqual(["once", "twice", "3 times"]);
  });

  it("tells a reopen apart from a submit in the history", () => {
    expect(complaintHistoryEntry("complaint.submitted", { complaint_no: "X/1" }).title).toBe(
      "Submitted",
    );
    expect(
      complaintHistoryEntry("complaint.submitted", {
        reopened: true,
        from: "qc_rejected",
        clock: "continue",
      }),
    ).toEqual({
      title: "Reopened after QC rejected it",
      detail: "Its targets run on",
      tone: "warning",
    });
  });
});
