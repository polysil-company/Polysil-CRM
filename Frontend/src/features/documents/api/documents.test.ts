import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { documentRefusal } from "@/features/documents/lib/document-refusals";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockDb, resetMockDb } from "@/mocks/db";

import {
  deleteDocument,
  getDocumentLink,
  listDocumentTypes,
  listDocuments,
  listLeadDocuments,
  uploadDocument,
} from "./documents.api";

let keys = 0;
function key(): string {
  keys += 1;
  return `documents-test-${String(keys)}`;
}

/** The order the mock seeds documents on, with its lead, quotation and first dispatch. */
function story(): { leadId: string; quotationId: string; orderId: string; dispatchId: string } {
  const order = mockDb.orders.find((item) =>
    mockDb.documents.some((document) => document.record_id === item.id),
  );
  const leadId = order?.lead?.id;
  const quotationId = order?.quotations[0]?.id;
  const dispatchId = order?.dispatches[0]?.id;
  if (
    order === undefined ||
    leadId === undefined ||
    quotationId === undefined ||
    dispatchId === undefined
  ) {
    throw new Error("No seeded story");
  }
  return { leadId, quotationId, orderId: order.id, dispatchId };
}

function pdf(name = "po.pdf", size = 2048): File {
  return new File([new Uint8Array(size)], name, { type: "application/pdf" });
}

async function refusal(call: Promise<unknown>): Promise<{ status: number; code: string | null }> {
  try {
    await call;
  } catch (error) {
    if (isApiError(error)) return { status: error.status ?? 0, code: error.code ?? null };
    throw error;
  }
  throw new Error("Expected the call to be refused");
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

describe("[DOC-001] Documents on a record", () => {
  beforeEach(reset);
  afterEach(reset);

  it("lists the types, Other needing a name", async () => {
    const types = await listDocumentTypes();
    expect(types.find((type) => type.code === "purchase_order")).toEqual({
      code: "purchase_order",
      label: "Purchase order",
      needsName: false,
    });
    expect(types.find((type) => type.code === "other")?.needsName).toBe(true);
  });

  it("lists one record's documents, and a lead's whole story with each record named", async () => {
    const { leadId, orderId } = story();
    const onOrder = await listDocuments("sales_order", orderId);
    expect(onOrder.map((document) => document.docType)).toEqual([
      "payment_proof",
      "purchase_order",
    ]);
    expect(onOrder[0]).toMatchObject({ name: "Advance, NEFT", preview: false, recordLabel: null });

    const onLead = await listLeadDocuments(leadId);
    expect(onLead.map((document) => document.recordType)).toEqual([
      "dispatch",
      "sales_order",
      "sales_order",
      "quotation",
      "lead",
    ]);
    expect(onLead.every((document) => document.recordLabel !== null)).toBe(true);
  });

  it("opens a document through a ten-minute link", async () => {
    const { orderId } = story();
    const [first] = await listDocuments("sales_order", orderId);
    const link = await getDocumentLink(first?.id ?? "");
    expect(link.url).not.toBe("");
    expect(Date.parse(link.expiresAt) - Date.now()).toBeGreaterThan(9 * 60_000);
  });

  it("answers a record that isn't there with 404", async () => {
    expect(await refusal(listDocuments("quotation", "no-such-quotation"))).toEqual({
      status: 404,
      code: "not_found",
    });
  });
});

describe("[DOC-002] Attach a document", () => {
  beforeEach(reset);
  afterEach(reset);

  it("attaches a file, and answers the same file again with the one already there", async () => {
    const { quotationId } = story();
    const input = {
      recordType: "quotation" as const,
      recordId: quotationId,
      docType: "purchase_order",
      name: "PO 4471",
      file: pdf(),
    };
    const made = await uploadDocument({ ...input, idempotencyKey: key() });
    expect(made).toMatchObject({
      recordType: "quotation",
      docTypeLabel: "Purchase order",
      name: "PO 4471",
      filename: "po.pdf",
      sizeBytes: 2048,
      preview: true,
      uploadedBy: { name: "Aarav Desai" },
    });
    const again = await uploadDocument({ ...input, idempotencyKey: key() });
    expect(again.id).toBe(made.id);
    expect(
      (await listDocuments("quotation", quotationId)).map((document) => document.id),
    ).toContain(made.id);
  });

  it("refuses Other without a name on the field, a type it can't take, and a file over 10 MB", async () => {
    const { orderId } = story();
    const unnamed = await uploadDocument({
      recordType: "sales_order",
      recordId: orderId,
      docType: "other",
      name: null,
      file: pdf(),
      idempotencyKey: key(),
    }).catch((error: unknown) => error);
    expect(readFieldErrors(unnamed)).toEqual({ name: "name the document" });
    expect(documentRefusal(unnamed).name).toBe("Name the document.");

    const text = await uploadDocument({
      recordType: "sales_order",
      recordId: orderId,
      docType: "invoice",
      name: null,
      file: new File(["hello"], "notes.txt", { type: "text/plain" }),
      idempotencyKey: key(),
    }).catch((error: unknown) => error);
    expect(documentRefusal(text).message).toBe("Only JPEG, PNG, WebP, HEIC or PDF files.");

    const big = await uploadDocument({
      recordType: "sales_order",
      recordId: orderId,
      docType: "invoice",
      name: null,
      file: pdf("big.pdf", 10 * 1024 * 1024 + 1),
      idempotencyKey: key(),
    }).catch((error: unknown) => error);
    expect(documentRefusal(big).message).toBe("Files up to 10 MB.");
  });

  it("keeps quotations to staff, and a merged lead or a voided dispatch closed", async () => {
    const { quotationId, dispatchId } = story();
    writeMockRole("dealer");
    expect(
      await refusal(
        uploadDocument({
          recordType: "quotation",
          recordId: quotationId,
          docType: "signed_quotation",
          name: null,
          file: pdf(),
          idempotencyKey: key(),
        }),
      ),
    ).toEqual({ status: 403, code: "forbidden" });

    writeMockRole("admin");
    const merged = mockDb.leads.find((lead) => lead.stage === "merged");
    if (merged === undefined) throw new Error("No merged lead");
    const onMerged = await uploadDocument({
      recordType: "lead",
      recordId: merged.id,
      docType: "site_photo",
      name: null,
      file: new File([new Uint8Array(64)], "farm.jpg", { type: "image/jpeg" }),
      idempotencyKey: key(),
    }).catch((error: unknown) => error);
    expect(documentRefusal(onMerged)).toMatchObject({ stale: true });

    for (const order of mockDb.orders) {
      for (const dispatch of order.dispatches) {
        if (dispatch.id === dispatchId) dispatch.voided_at = "2026-10-10T05:00:00Z";
      }
    }
    expect(
      await refusal(
        uploadDocument({
          recordType: "dispatch",
          recordId: dispatchId,
          docType: "delivery_challan",
          name: null,
          file: pdf(),
          idempotencyKey: key(),
        }),
      ),
    ).toEqual({ status: 409, code: "record_closed" });
  });
});

describe("[DOC-003] Remove a document", () => {
  beforeEach(reset);
  afterEach(reset);

  it("lets staff who may add remove one, which leaves the list", async () => {
    const { orderId } = story();
    const [first] = await listDocuments("sales_order", orderId);
    await deleteDocument({ documentId: first?.id ?? "", idempotencyKey: key() });
    expect(
      (await listDocuments("sales_order", orderId)).map((document) => document.id),
    ).not.toContain(first?.id);
  });

  it("refuses a partner user someone else's document", async () => {
    const { leadId } = story();
    const onLead = (await listDocuments("lead", leadId))[0];
    writeMockRole("dealer");
    expect(
      await refusal(deleteDocument({ documentId: onLead?.id ?? "", idempotencyKey: key() })),
    ).toEqual({ status: 403, code: "forbidden" });
  });
});
