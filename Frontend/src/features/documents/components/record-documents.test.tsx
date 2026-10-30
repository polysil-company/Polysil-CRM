import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { RecordDocuments, type RecordDocumentsProps } from "./record-documents";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(props: RecordDocumentsProps): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <RecordDocuments {...props} />
      <Toaster />
    </>,
  );
  return user;
}

function story(): { leadId: string; orderId: string } {
  const order = mockDb.orders.find((item) =>
    mockDb.documents.some((document) => document.record_id === item.id),
  );
  if (order?.lead === undefined || order.lead === null) throw new Error("No seeded story");
  return { leadId: order.lead.id, orderId: order.id };
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

describe("[DOC-001] RecordDocuments", () => {
  beforeEach(reset);
  afterEach(reset);

  it("lists an order's documents, each opened by its link, and HEIC offered as a download", async () => {
    signInAs("admin");
    const { orderId } = story();
    show({ scope: { kind: "record", recordType: "sales_order", recordId: orderId }, canAdd: true });
    const list = await screen.findByRole("list", { name: "Documents" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Advance, NEFT");
    expect(rows[0]).toHaveTextContent("Payment slip or receipt");
    expect(rows[0]).toHaveTextContent("IMG_4412.HEIC · 2.3 MB");
    expect(
      await within(list).findByRole("link", { name: /^Download Advance, NEFT/ }),
    ).toHaveAttribute("href", "/icon.png");
    expect(await within(list).findByRole("link", { name: /^Open Purchase order/ })).toHaveAttribute(
      "target",
      "_blank",
    );
  });

  it("shows a lead's whole story, each document naming its record", async () => {
    signInAs("admin");
    const { leadId } = story();
    show({ scope: { kind: "lead", leadId }, canAdd: true });
    const list = await screen.findByRole("list", { name: "Documents" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(5);
    expect(within(list).getByRole("link", { name: /^Quotation / })).toHaveAttribute(
      "href",
      expect.stringMatching(/^\/quotations\//),
    );
    expect(within(list).getByText(/^Dispatch /)).toBeInTheDocument();
    expect(
      screen.getByText("On this lead and on its quotations, orders and dispatches"),
    ).toBeInTheDocument();
  });

  it("offers nothing to add without permission, or on a closed record", async () => {
    signInAs("admin");
    const { orderId } = story();
    show({
      scope: { kind: "record", recordType: "sales_order", recordId: orderId },
      canAdd: true,
      closed: true,
    });
    await screen.findByRole("list", { name: "Documents" });
    expect(screen.queryByRole("button", { name: "Attach a file" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Remove/ })).not.toBeInTheDocument();
  });
});

describe("[DOC-002] Attach a file", () => {
  beforeEach(reset);
  afterEach(reset);

  it("names what is missing, asks Other for a name, then attaches the file", async () => {
    signInAs("admin");
    const quotation = mockDb.quotations[0];
    if (quotation === undefined) throw new Error("No quotation");
    const user = show({
      scope: { kind: "record", recordType: "quotation", recordId: quotation.id },
      canAdd: true,
    });
    expect(
      await screen.findByText(
        "No documents yet. Attach the purchase order, a payment slip or a photo.",
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Attach a file" }));
    const dialog = await screen.findByRole("dialog", { name: "Attach a file" });
    await user.click(within(dialog).getByRole("button", { name: "Attach" }));
    expect(within(dialog).getByText("Choose what it is.")).toBeInTheDocument();
    expect(within(dialog).getByText("Choose a file.")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("combobox", { name: "What it is" }));
    await user.click(await screen.findByRole("option", { name: "Other" }));
    expect(within(dialog).getByText("Name the document.")).toBeInTheDocument();
    await user.type(within(dialog).getByRole("textbox", { name: "Name" }), "Borewell report");
    await user.upload(
      within(dialog).getByTestId("document-file-input"),
      new File([new Uint8Array(4096)], "report.pdf", { type: "application/pdf" }),
    );
    expect(within(dialog).getByText("report.pdf · 4 KB")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Attach" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(await screen.findByText("Attached")).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Documents" });
    expect(within(list).getByText("Borewell report")).toBeInTheDocument();
    expect(mockDb.documents[0]).toMatchObject({ record_id: quotation.id, doc_type: "other" });
  });

  it("refuses a file that isn't a photo or a PDF before sending it", async () => {
    signInAs("admin");
    const { orderId } = story();
    const user = show({
      scope: { kind: "record", recordType: "sales_order", recordId: orderId },
      canAdd: true,
    });
    await user.click(await screen.findByRole("button", { name: "Attach a file" }));
    const dialog = await screen.findByRole("dialog", { name: "Attach a file" });
    await user.click(within(dialog).getByRole("combobox", { name: "What it is" }));
    await user.click(await screen.findByRole("option", { name: "Invoice" }));
    // A picker that ignores `accept` (some phones) still hands over any file.
    fireEvent.change(within(dialog).getByTestId("document-file-input"), {
      target: { files: [new File(["x"], "invoice.docx", { type: "application/msword" })] },
    });
    await user.click(within(dialog).getByRole("button", { name: "Attach" }));
    expect(
      within(dialog).getByText("Only JPEG, PNG, WebP, HEIC or PDF files."),
    ).toBeInTheDocument();
  });
});

describe("[DOC-003] Remove a document", () => {
  beforeEach(reset);
  afterEach(reset);

  it("asks first, then takes it off the list", async () => {
    signInAs("admin");
    const { orderId } = story();
    const user = show({
      scope: { kind: "record", recordType: "sales_order", recordId: orderId },
      canAdd: true,
    });
    await user.click(await screen.findByRole("button", { name: "Remove Purchase order" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove this document?" });
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));

    expect(await screen.findByText("Document removed")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        within(screen.getByRole("list", { name: "Documents" })).getAllByRole("listitem"),
      ).toHaveLength(1);
    });
  });
});
