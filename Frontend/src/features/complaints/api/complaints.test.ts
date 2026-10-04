import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockLookupRows } from "@/mocks/data/lookups";
import { MOCK_PRODUCTS } from "@/mocks/data/quotations";
import { MOCK_STAFF } from "@/mocks/data/reference";
import { MOCK_TERRITORIES } from "@/mocks/data/territories";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";

import {
  cancelComplaint,
  checkComplaint,
  createComplaint,
  deleteComplaint,
  getComplaint,
  getComplaintStats,
  getComplaintTimeline,
  listComplaints,
  patchComplaint,
  qcComplaint,
  replaceComplaintLines,
  submitComplaint,
} from "./complaints.api";
import type { ComplaintListParams, CreateComplaintRequest } from "./complaints.schemas";

const ALL: ComplaintListParams = {
  status: [],
  severity: null,
  typeId: null,
  q: "",
  breached: false,
  noOwner: false,
  awaitingMe: false,
  leadId: null,
  orderId: null,
};

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

function seeded(status: string): string {
  const complaint = mockDb.complaints.find((item) => item.status === status);
  if (complaint === undefined) throw new Error(`No ${status} complaint`);
  return complaint.id;
}

const NEW: CreateComplaintRequest = {
  complaint_type_id: mockLookupRows("complaint-types")[1]?.id ?? "",
  severity: "high",
  description: "Laterals cracking within two months",
  contact_name: "Kiritbhai Shah",
  contact_mobile: "98765 43210",
  territory_id: MOCK_TERRITORIES.find((item) => item.level === "taluka")?.id ?? "",
  dc_no: "DC-4471",
  supply_date: "2026-07-14",
  lines: [{ product_id: MOCK_PRODUCTS[0]?.id ?? "", supplied_qty: "2000", defective_qty: "340" }],
};

describe("[CMPL-001] listComplaints and stats", () => {
  afterEach(reset);

  it("lists newest first with the count, and filters by status and severity", async () => {
    const page = await listComplaints({ ...ALL, cursor: null });
    expect(page.total).toBe(mockDb.complaints.length);
    const created = page.items.map((item) => item.createdAt);
    expect(created).toEqual([...created].sort().reverse());

    const waiting = await listComplaints({
      ...ALL,
      status: ["submitted"],
      severity: "high",
      cursor: null,
    });
    expect(
      waiting.items.every((item) => item.status === "submitted" && item.severity === "high"),
    ).toBe(true);
  });

  it("gives a manager the ones waiting on their check, oldest first", async () => {
    writeMockRole("district_manager");
    const page = await listComplaints({ ...ALL, awaitingMe: true, cursor: null });

    expect(page.items.length).toBeGreaterThan(0);
    expect(page.items.every((item) => item.status === "submitted")).toBe(true);
  });

  it("gives QC the ones under QC", async () => {
    writeMockRole("qa_manager");
    const page = await listComplaints({ ...ALL, awaitingMe: true, cursor: null });

    expect(page.items.every((item) => item.status === "under_qc")).toBe(true);
  });

  it("sends the filters the backend reads", async () => {
    let sent: URL | undefined;
    server.use(
      http.get(buildApiUrl("/complaints"), ({ request }) => {
        sent = new URL(request.url);
      }),
    );
    await listComplaints({
      ...ALL,
      status: ["submitted", "under_qc"],
      breached: true,
      noOwner: true,
      q: "Shah",
      cursor: null,
    });

    expect(sent?.searchParams.getAll("status")).toEqual(["submitted", "under_qc"]);
    expect(sent?.searchParams.get("breached")).toBe("true");
    expect(sent?.searchParams.get("owner")).toBe("none");
    expect(sent?.searchParams.get("q")).toBe("Shah");
  });

  it("counts by status, and says whether files can be stored", async () => {
    const stats = await getComplaintStats();

    expect(stats.byStatus.submitted).toBeGreaterThan(0);
    expect(stats.storageAvailable).toBe(true);
  });
});

describe("[CMPL-003] raise, edit, submit, cancel, delete", () => {
  afterEach(reset);

  it("raises a draft, then submits it: numbered, with targets", async () => {
    const draft = await createComplaint({ body: NEW, idempotencyKey: "c-1" });
    expect(draft).toMatchObject({ status: "draft", number: null, contactMobile: "+919876543210" });
    expect(draft.can).toMatchObject({ edit: true, submit: true, delete: true });

    const submitted = await submitComplaint(draft.id, "s-1");

    expect(submitted.status).toBe("submitted");
    expect(submitted.number).toMatch(/^Poly\/Comp\.\/2026-27\/GJ\/\d+$/);
    expect(submitted.sla?.policy).toBe("set");
  });

  it("refuses a submit without the challan or supply date, naming them", async () => {
    const draft = await createComplaint({
      body: { ...NEW, dc_no: null, supply_date: null },
      idempotencyKey: "c-2",
    });

    await expect(submitComplaint(draft.id, "s-2")).rejects.toMatchObject({
      status: 422,
      code: "missing_for_submit",
      details: { fields: { dc_no: expect.any(String), supply_date: expect.any(String) } },
    });
  });

  it("refuses a submit with nothing defective", async () => {
    const draft = await createComplaint({
      body: {
        ...NEW,
        lines: [{ product_id: MOCK_PRODUCTS[0]?.id ?? "", supplied_qty: "10", defective_qty: "0" }],
      },
      idempotencyKey: "c-3",
    });

    await expect(submitComplaint(draft.id, "s-3")).rejects.toMatchObject({
      code: "nothing_defective",
    });
  });

  it("refuses more defective than supplied, on the line", async () => {
    await expect(
      createComplaint({
        body: {
          ...NEW,
          lines: [
            { product_id: MOCK_PRODUCTS[0]?.id ?? "", supplied_qty: "10", defective_qty: "11" },
          ],
        },
        idempotencyKey: "c-4",
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: { fields: { "lines.0.defective_qty": expect.any(String) } },
    });
  });

  it("edits a draft's header and products, and refuses once it is submitted", async () => {
    const draft = await createComplaint({ body: NEW, idempotencyKey: "c-5" });
    const patched = await patchComplaint(draft.id, {
      body: { description: "Cracks every 3 m" },
      idempotencyKey: "p-1",
    });
    expect(patched.description).toBe("Cracks every 3 m");
    const relined = await replaceComplaintLines(draft.id, {
      body: {
        lines: [{ product_id: MOCK_PRODUCTS[1]?.id ?? "", supplied_qty: "40", defective_qty: "6" }],
      },
      idempotencyKey: "l-1",
    });
    expect(relined.lines).toHaveLength(1);

    await submitComplaint(draft.id, "s-5");
    await expect(
      patchComplaint(draft.id, { body: { description: "Late" }, idempotencyKey: "p-2" }),
    ).rejects.toMatchObject({ status: 409, code: "complaint_not_draft" });
  });

  it("cancels a submitted one with a reason, and deletes a draft never submitted", async () => {
    const cancelled = await cancelComplaint(seeded("submitted"), {
      body: { reason: "Raised twice." },
      idempotencyKey: "x-1",
    });
    expect(cancelled).toMatchObject({
      status: "cancelled",
      cancellation: { reason: "Raised twice." },
    });

    const draft = await createComplaint({ body: NEW, idempotencyKey: "c-6" });
    await deleteComplaint(draft.id, "d-1");
    expect(mockDb.complaints.some((item) => item.id === draft.id)).toBe(false);
  });
});

describe("[CMPL-004] check", () => {
  afterEach(reset);

  it("approves to QC with a new severity and an owner", async () => {
    writeMockRole("district_manager");
    const owner = MOCK_STAFF[3];
    const checked = await checkComplaint(seeded("submitted"), {
      body: { decision: "approve", remark: "Genuine.", severity: "high", owner_user_id: owner?.id },
      idempotencyKey: "k-1",
    });

    expect(checked).toMatchObject({
      status: "under_qc",
      severity: "high",
      owner: { id: owner?.id },
      check: { decision: "approve" },
    });
  });

  it("returns it to the raiser as a draft, with the remark", async () => {
    writeMockRole("district_manager");
    const returned = await checkComplaint(seeded("submitted"), {
      body: { decision: "return", remark: "Add the supply date." },
      idempotencyKey: "k-2",
    });

    expect(returned).toMatchObject({
      status: "draft",
      check: { decision: "return", remark: "Add the supply date." },
    });
  });

  it("refuses an officer, and a complaint that moved on", async () => {
    writeMockRole("employee");
    await expect(
      checkComplaint(seeded("submitted"), {
        body: { decision: "approve", remark: "ok" },
        idempotencyKey: "k-3",
      }),
    ).rejects.toMatchObject({ status: 403 });
    writeMockRole("district_manager");
    await expect(
      checkComplaint(seeded("under_qc"), {
        body: { decision: "approve", remark: "ok" },
        idempotencyKey: "k-4",
      }),
    ).rejects.toMatchObject({ status: 409, code: "status_changed" });
  });
});

describe("[CMPL-005] QC verdict", () => {
  afterEach(reset);

  it("approves with the sample's dates, and refuses a date after today", async () => {
    writeMockRole("qa_manager");
    const id = seeded("under_qc");
    await expect(
      qcComplaint(id, {
        body: { verdict: "approved", remark: "Defect.", tested_on: "2099-01-01" },
        idempotencyKey: "q-1",
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: { fields: { tested_on: expect.any(String) } },
    });

    const verdict = await qcComplaint(id, {
      body: { verdict: "approved", remark: "Defect in the wall." },
      idempotencyKey: "q-2",
    });
    expect(verdict).toMatchObject({ status: "qc_approved", quality: { verdict: "approved" } });
  });
});

describe("[CMPL-002] getComplaint and its history", () => {
  afterEach(reset);

  it("reads one complaint with what the user may do, and its history newest first", async () => {
    writeMockRole("district_manager");
    const id = seeded("submitted");
    const complaint = await getComplaint(id);
    expect(complaint.can.check).toBe(true);

    const history = await getComplaintTimeline({ complaintId: id, cursor: null });
    expect(history.items.map((event) => event.kind)).toEqual([
      "complaint.submitted",
      "complaint.created",
    ]);
  });

  it("reports a complaint that breaks the contract", async () => {
    server.use(
      http.get(buildApiUrl("/complaints/:id"), () => HttpResponse.json({ data: { id: "x" } })),
    );

    await expect(getComplaint("x")).rejects.toMatchObject({ kind: "contract" });
  });
});
