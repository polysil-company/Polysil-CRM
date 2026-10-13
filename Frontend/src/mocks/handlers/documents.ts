import { http, HttpResponse } from "msw";

import {
  DOCUMENT_CONTENT_TYPES,
  DOCUMENT_MAX_BYTES,
  DOCUMENT_NAME_MAX,
  DOCUMENTS_PER_RECORD,
  RECORD_TYPES,
  type RecordDocumentWire,
  type RecordType,
} from "@/features/documents/api/documents.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import {
  MOCK_DOCUMENT_TYPES,
  mockDocumentTypeLabel,
  type MockDocument,
} from "@/mocks/data/documents";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, mockUuid } from "@/mocks/data/reference";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse, readMultipart } from "./shared";

/**
 * DOC-001…003 · Documents on records (`docs/api/documents.md`, handover
 * `documents-and-replacement-chain.md`). Who adds: leads and orders, whoever edits them;
 * quotations, staff only; dispatches, Dispatch or the order's editor. A merged lead and a
 * voided dispatch take no more (`409 record_closed`). The uploader, or staff who may add to
 * the record, removes one. The mock reads the content type the browser names, not the bytes.
 */

interface MockRecord {
  readonly label: string | null;
  readonly closed: boolean;
}

/** The record a document sits on, or undefined when there is none. */
function recordOf(type: RecordType, id: string): MockRecord | undefined {
  switch (type) {
    case "lead": {
      const lead = mockDb.leads.find((item) => item.id === id);
      return lead === undefined
        ? undefined
        : { label: lead.inquiry_no, closed: lead.stage === "merged" };
    }
    case "quotation": {
      const quotation = mockDb.quotations.find((item) => item.id === id);
      return quotation === undefined ? undefined : { label: quotation.quote_no, closed: false };
    }
    case "sales_order": {
      const order = mockDb.orders.find((item) => item.id === id);
      return order === undefined ? undefined : { label: order.order_no, closed: false };
    }
    case "dispatch": {
      const dispatch = mockDb.orders
        .flatMap((order) => order.dispatches)
        .find((item) => item.id === id);
      return dispatch === undefined
        ? undefined
        : { label: dispatch.dispatch_no, closed: dispatch.voided_at !== null };
    }
    default:
      return undefined;
  }
}

function mayAdd(type: RecordType): boolean {
  const role = readMockRole();
  const permissions = mockPermissionsFor(role);
  switch (type) {
    case "lead":
      return can(permissions, "leads", "edit");
    case "quotation":
      return !isPartnerRole(role) && can(permissions, "quotations", "edit");
    case "sales_order":
      return can(permissions, "sales_orders", "edit");
    case "dispatch":
      return can(permissions, "dispatch", "create") || can(permissions, "sales_orders", "edit");
    case "payment":
      return can(permissions, "accounts", "edit");
    default:
      return false;
  }
}

function me(): { id: string; full_name: string } {
  const data = mockMeFor(readMockRole()).data;
  return { id: data.id, full_name: data.full_name };
}

function isRecordType(value: unknown): value is RecordType {
  return RECORD_TYPES.some((type) => type === value);
}

function wireOf(document: MockDocument, withLabel: boolean): RecordDocumentWire {
  const { fingerprint: _fingerprint, removed: _removed, ...wire } = document;
  return {
    ...wire,
    record_label: withLabel
      ? (recordOf(document.record_type, document.record_id)?.label ?? null)
      : null,
  };
}

function live(): MockDocument[] {
  return mockDb.documents.filter((document) => !document.removed);
}

/** The uploaded file as a link; a stand-in where the runtime can't make one (jsdom), or seeded. */
function linkFor(documentId: string): string {
  const file = mockDb.documentFiles.get(documentId);
  if (file === undefined) return "/icon.svg";
  try {
    return URL.createObjectURL(file);
  } catch {
    return "/icon.svg";
  }
}

function notFound(): Response {
  return errorResponse(404, "not_found", "No such record or document, or not visible to you.");
}

function closed(): Response {
  return errorResponse(409, "record_closed", "This record takes no more documents.");
}

export const documentHandlers = [
  http.get(buildApiUrl("/documents/types"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    return HttpResponse.json({ data: MOCK_DOCUMENT_TYPES });
  }),

  http.get(buildApiUrl("/documents"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const params = new URL(request.url).searchParams;
    const type = params.get("record_type");
    const id = params.get("record_id") ?? "";
    if (!isRecordType(type)) {
      return errorResponse(422, "validation_error", "Check the fields.", {
        record_type: "not a record type",
      });
    }
    if (recordOf(type, id) === undefined) return notFound();
    const rows =
      scenario === "empty"
        ? []
        : live().filter((document) => document.record_type === type && document.record_id === id);
    return HttpResponse.json({ data: rows.map((document) => wireOf(document, false)) });
  }),

  http.get(buildApiUrl("/leads/:leadId/documents"), async ({ params }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const leadId = String(params.leadId);
    if (recordOf("lead", leadId) === undefined) return notFound();
    // The lead, leads merged into it, their quotations, those quotations' orders and dispatches.
    const leadIds = new Set([
      leadId,
      ...mockDb.leads.filter((lead) => lead.merged_into?.id === leadId).map((lead) => lead.id),
    ]);
    const quotationIds = new Set(
      mockDb.quotations
        .filter((quotation) => quotation.lead !== null && leadIds.has(quotation.lead.id))
        .map((quotation) => quotation.id),
    );
    const orders = mockDb.orders.filter(
      (order) => order.lead !== null && leadIds.has(order.lead.id),
    );
    const orderIds = new Set(orders.map((order) => order.id));
    const dispatchIds = new Set(orders.flatMap((order) => order.dispatches.map((item) => item.id)));
    const mine = (document: MockDocument): boolean => {
      switch (document.record_type) {
        case "lead":
          return leadIds.has(document.record_id);
        case "quotation":
          return quotationIds.has(document.record_id);
        case "sales_order":
          return orderIds.has(document.record_id);
        case "dispatch":
          return dispatchIds.has(document.record_id);
        default:
          return false;
      }
    };
    const rows = scenario === "empty" ? [] : live().filter(mine);
    return HttpResponse.json({ data: rows.map((document) => wireOf(document, true)) });
  }),

  http.post(buildApiUrl("/documents"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (request.headers.get("idempotency-key") === null) {
      return errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.");
    }
    const form = await readMultipart(request);
    const type = form.get("record_type");
    const recordId = form.get("record_id");
    const docType = form.get("doc_type");
    const nameField = form.get("name");
    const file = form.get("file");
    if (!isRecordType(type) || typeof recordId !== "string") {
      return errorResponse(422, "validation_error", "Check the fields.", {
        record_type: "not a record type",
      });
    }
    if (typeof docType !== "string" || mockDocumentTypeLabel(docType) === undefined) {
      return errorResponse(422, "validation_error", "Check the fields.", {
        doc_type: "not a document type",
      });
    }
    if (file === undefined || typeof file === "string") {
      return errorResponse(422, "validation_error", "Check the fields.", {
        file: "Field required",
      });
    }
    if (file.size > DOCUMENT_MAX_BYTES) {
      return errorResponse(413, "attachment_too_large", "Up to 10 MB.");
    }
    if (file.size === 0) {
      return errorResponse(422, "validation_error", "Check the fields.", { file: "empty" });
    }
    const name = typeof nameField === "string" && nameField.trim() !== "" ? nameField.trim() : null;
    if (docType === "other" && name === null) {
      return errorResponse(422, "validation_error", "Check the fields.", {
        name: "name the document",
      });
    }
    if (name !== null && name.length > DOCUMENT_NAME_MAX) {
      return errorResponse(422, "validation_error", "Check the fields.", {
        name: "1 to 80 characters",
      });
    }
    const heic = file.type === "" && /\.(heic|heif)$/i.test(file.name);
    if (!heic && !DOCUMENT_CONTENT_TYPES.some((accepted) => accepted === file.type)) {
      return errorResponse(422, "attachment_type", "JPEG, PNG, WebP, HEIC or PDF only.", {
        file: "not an allowed type",
      });
    }
    // Who may add comes first, a repeat included (backend code review 5).
    const record = recordOf(type, recordId);
    if (record === undefined) return notFound();
    if (!mayAdd(type)) {
      return errorResponse(403, "forbidden", "You may not add documents to this record.");
    }
    if (record.closed) return closed();
    const fingerprint = `${file.name}:${String(file.size)}`;
    const onRecord = live().filter(
      (document) => document.record_type === type && document.record_id === recordId,
    );
    const same = onRecord.find(
      (document) => document.doc_type === docType && document.fingerprint === fingerprint,
    );
    if (same !== undefined) return HttpResponse.json({ data: wireOf(same, false) });
    if (onRecord.length >= DOCUMENTS_PER_RECORD) {
      return errorResponse(422, "too_many_documents", "Up to 50 documents on one record.");
    }
    const contentType = heic ? "image/heic" : file.type;
    const document: MockDocument = {
      id: mockUuid(MOCK_ID_SPACE.document, 0x1000 + mockDb.documents.length + 1),
      record_type: type,
      record_id: recordId,
      record_label: null,
      doc_type: docType,
      doc_type_label: mockDocumentTypeLabel(docType) ?? docType,
      name,
      filename: file.name,
      content_type: contentType,
      size_bytes: file.size,
      preview: contentType !== "image/heic" && contentType !== "image/heif",
      uploaded_by: me(),
      uploaded_at: new Date().toISOString(),
      fingerprint,
      removed: false,
    };
    mockDb.documents.unshift(document);
    mockDb.documentFiles.set(
      document.id,
      new Blob([Uint8Array.from(file.bytes)], { type: contentType }),
    );
    return HttpResponse.json({ data: wireOf(document, false) }, { status: 201 });
  }),

  http.get(buildApiUrl("/documents/:documentId/link"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const document = live().find((item) => item.id === params.documentId);
    if (document === undefined) return notFound();
    return HttpResponse.json({
      data: {
        url: linkFor(document.id),
        expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
        filename: document.filename,
        content_type: document.content_type,
      },
    });
  }),

  http.delete(buildApiUrl("/documents/:documentId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (request.headers.get("idempotency-key") === null) {
      return errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.");
    }
    const document = live().find((item) => item.id === params.documentId);
    if (document === undefined) return notFound();
    const record = recordOf(document.record_type, document.record_id);
    if (record?.closed === true) return closed();
    const staff = !isPartnerRole(readMockRole());
    const uploader = document.uploaded_by?.id === me().id;
    if (!uploader && !(staff && mayAdd(document.record_type))) {
      return errorResponse(403, "forbidden", "You may not remove that document.");
    }
    document.removed = true;
    return new HttpResponse(null, { status: 204 });
  }),
];
