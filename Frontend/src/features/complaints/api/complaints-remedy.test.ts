import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { decideApprovalStep, listPendingApprovals } from "@/features/approvals/api/approvals.api";
import { buildApiUrl } from "@/lib/api/url";
import { ROLES, type Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";

import {
  chooseRemedy,
  createSlaPolicy,
  deleteAttachment,
  exportComplaints,
  getAttachmentLink,
  getComplaint,
  getComplaintTimeline,
  listSlaPolicies,
  uploadAttachment,
  withdrawRemedy,
} from "./complaints.api";

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

function seeded(status: string): string {
  const complaint = mockDb.complaints.find((item) => item.status === status);
  if (complaint === undefined) throw new Error(`No ${status} complaint`);
  return complaint.id;
}

function asRole(value: string): Role {
  const role = ROLES.find((known) => known === value);
  if (role === undefined) throw new Error(`Not a role: ${value}`);
  return role;
}

/** Signs in as `role` and decides the one step waiting on it for this complaint. */
async function decide(
  role: Role,
  complaintId: string,
  decision: "approve" | "reject",
  remark?: string,
): Promise<void> {
  writeMockRole(role);
  // The refund's step joins the end of a queue full of seeded orders.
  const queue = await listPendingApprovals({ cursor: null, includeBelow: false, limit: 100 });
  const row = queue.items.find((item) => item.document.id === complaintId);
  if (row === undefined) throw new Error(`Nothing waits on ${role}`);
  expect(row.docType).toBe("complaint");
  await decideApprovalStep(row.stepId, {
    body: { decision, remark: remark ?? null },
    idempotencyKey: `${role}-${decision}`,
  });
}

describe("[CMPL-007] chooseRemedy and withdrawRemedy", () => {
  afterEach(reset);

  it("sends a refund up the managers by amount, then Accounts pays it and it closes", async () => {
    writeMockRole("qa_manager");
    const id = seeded("qc_approved");
    const pending = await chooseRemedy(id, {
      body: { kind: "refund", amount: "1500.00", payee_name: "Kiritbhai Shah", remark: "Burst" },
      idempotencyKey: "r-1",
    });
    expect(pending).toMatchObject({
      status: "remedy_pending",
      remedy: { kind: "refund", status: "pending", refund: { amount: "1500.00" } },
      can: { withdraw: true, remedy: false },
    });
    const roles = pending.remedy?.refund?.approval?.steps.map((step) => step.role);
    expect(roles?.at(-1)).toBe("account_manager");

    for (const role of roles?.slice(0, -1) ?? []) {
      await decide(asRole(role), id, "approve");
    }
    // Accounts' remark is the payment reference.
    await decide("account_manager", id, "approve", "UTR 0042");

    writeMockRole("qa_manager");
    const closed = await getComplaint(id);
    expect(closed).toMatchObject({
      status: "closed",
      remedy: { status: "completed", refund: { paymentReference: "UTR 0042" } },
    });
    const history = await getComplaintTimeline({ complaintId: id, cursor: null });
    expect(history.items.map((event) => event.kind).slice(0, 3)).toEqual([
      "complaint.closed",
      "complaint.refund_paid",
      "complaint.refund_requested",
    ]);
  });

  it("returns a refund turned down at approval to QC to choose again", async () => {
    writeMockRole("qa_manager");
    const id = seeded("qc_approved");
    await chooseRemedy(id, {
      body: { kind: "refund", amount: "800", payee_name: "Dealer", remark: "Leak" },
      idempotencyKey: "r-2",
    });
    const first = (await getComplaint(id)).remedy?.refund?.approval?.steps[0]?.role;
    await decide(
      first === "district_manager" ? "district_manager" : "admin",
      id,
      "reject",
      "Too much",
    );

    writeMockRole("qa_manager");
    expect(await getComplaint(id)).toMatchObject({
      status: "qc_approved",
      remedy: { status: "rejected" },
      can: { remedy: true },
    });
  });

  it("refuses a refund without an amount, and anyone but QC", async () => {
    const id = seeded("qc_approved");
    writeMockRole("district_manager");
    await expect(
      chooseRemedy(id, { body: { kind: "none", remark: "x" }, idempotencyKey: "r-3" }),
    ).rejects.toMatchObject({ status: 403 });

    writeMockRole("qa_manager");
    await expect(
      chooseRemedy(id, {
        body: { kind: "refund", payee_name: "A", remark: "x" },
        idempotencyKey: "r-4",
      }),
    ).rejects.toMatchObject({ status: 422, details: { fields: { amount: expect.any(String) } } });
  });

  it("closes at once with no remedy, and withdraws an open one", async () => {
    writeMockRole("qa_manager");
    const id = seeded("qc_approved");
    const replacement = await chooseRemedy(id, {
      body: { kind: "replacement", remark: "Send new laterals" },
      idempotencyKey: "r-5",
    });
    expect(replacement.remedy?.replacementOrder).not.toBeNull();

    const back = await withdrawRemedy(id, {
      body: { remark: "Wrong size" },
      idempotencyKey: "w-1",
    });
    expect(back).toMatchObject({ status: "qc_approved", remedy: { status: "withdrawn" } });

    const none = await chooseRemedy(id, {
      body: { kind: "none", remark: "Goodwill only" },
      idempotencyKey: "r-6",
    });
    expect(none).toMatchObject({ status: "closed", remedy: { kind: "none", status: "completed" } });
  });
});

describe("[CMPL-006] attachments", () => {
  afterEach(reset);

  // jsdom can't stream a File through fetch, so these read the request's headers only; the
  // mock's own checks on the file are walked through in the browser.
  it("sends the file as multipart with its kind, never as JSON", async () => {
    const id = seeded("draft");
    const seen: { contentType: string | null; key: string | null }[] = [];
    server.use(
      http.post(buildApiUrl("/complaints/:id/attachments"), ({ request }) => {
        seen.push({
          contentType: request.headers.get("content-type"),
          key: request.headers.get("idempotency-key"),
        });
        return HttpResponse.json({ data: { id: "a-1" } }, { status: 201 });
      }),
    );
    const file = new File(["jpeg bytes"], "crack.jpg", { type: "image/jpeg" });
    await uploadAttachment({ complaintId: id, file, kind: "photo", idempotencyKey: "u-1" });

    expect(seen).toEqual([
      { contentType: expect.stringMatching(/^multipart\/form-data; boundary=/), key: "u-1" },
    ]);
  });

  it("says why a file was refused", async () => {
    const id = seeded("draft");
    server.use(
      http.post(buildApiUrl("/complaints/:id/attachments"), () =>
        HttpResponse.json(
          { error: { code: "attachment_type", message: "JPEG, PNG, WebP, HEIC or PDF only." } },
          { status: 422 },
        ),
      ),
    );
    const file = new File(["text"], "notes.txt", { type: "text/plain" });
    await expect(
      uploadAttachment({ complaintId: id, file, kind: "document", idempotencyKey: "u-2" }),
    ).rejects.toMatchObject({ status: 422, code: "attachment_type" });
  });

  it("links to a file for ten minutes, and removes it", async () => {
    const complaint = mockDb.complaints.find((item) => item.status === "draft");
    if (complaint === undefined) throw new Error("No draft");
    complaint.attachments.push({
      id: "a-seeded",
      kind: "photo",
      filename: "crack.jpg",
      content_type: "image/jpeg",
      size_bytes: 2048,
      preview: true,
      uploaded_by: null,
      uploaded_at: new Date().toISOString(),
    });

    const link = await getAttachmentLink(complaint.id, "a-seeded");
    expect(link.url).not.toBe("");

    await deleteAttachment(complaint.id, "a-seeded", "d-1");
    expect((await getComplaint(complaint.id)).attachments).toHaveLength(0);
  });
});

describe("[CMPL-009] exportComplaints", () => {
  afterEach(reset);

  it("downloads the list as a dated workbook", async () => {
    const file = await exportComplaints({
      status: [],
      severity: null,
      typeId: null,
      q: "",
      breached: false,
      noOwner: false,
      awaitingMe: false,
      leadId: null,
      orderId: null,
    });
    expect(file.filename).toMatch(/^complaints-\d{4}-\d{2}-\d{2}\.xlsx$/);
  });
});

describe("[CMPL-008] targets", () => {
  afterEach(reset);

  it("sets a new target from a day; the one in force ends that day", async () => {
    writeMockRole("admin");
    const before = await listSlaPolicies();
    expect(before.filter((policy) => policy.effectiveTo === null)).toHaveLength(3);

    const from = todayInIndia();
    const after = await createSlaPolicy({
      body: { severity: "high", response_hours: 2, resolution_hours: 9, effective_from: from },
      idempotencyKey: "s-1",
    });
    const high = after.filter((policy) => policy.severity === "high");
    expect(high).toHaveLength(2);
    expect(high.find((policy) => policy.responseHours === 4)?.effectiveTo).toBe(from);
  });

  it("refuses a day in the past, and anyone who may not edit masters", async () => {
    writeMockRole("admin");
    await expect(
      createSlaPolicy({
        body: {
          severity: "low",
          response_hours: 2,
          resolution_hours: 9,
          effective_from: "2020-01-01",
        },
        idempotencyKey: "s-2",
      }),
    ).rejects.toMatchObject({ code: "target_in_the_past" });

    writeMockRole("employee");
    await expect(
      createSlaPolicy({
        body: {
          severity: "low",
          response_hours: 2,
          resolution_hours: 9,
          effective_from: todayInIndia(),
        },
        idempotencyKey: "s-3",
      }),
    ).rejects.toMatchObject({ status: 403 });
  });
});
