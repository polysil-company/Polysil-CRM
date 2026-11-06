import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { getComplaint, getComplaintPdf } from "@/features/complaints/api/complaints.api";
import { isApiError } from "@/lib/api/errors";
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
  vi.unstubAllGlobals();
}

/** The new tab the button opens on the click, before the link arrives. */
function stubNewTab(): {
  closed: boolean;
  opener: unknown;
  location: { href: string };
  close: () => void;
} {
  const tab = { closed: false, opener: {}, location: { href: "" }, close: vi.fn() };
  vi.stubGlobal(
    "open",
    vi.fn(() => tab),
  );
  return tab;
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

describe("[CMPL-013] A complaint's PDF (contract)", () => {
  afterEach(reset);

  it("has none for a draft, and a ten-minute link once submitted", async () => {
    const draft = seeded("draft");
    expect((await getComplaint(draft)).pdfState).toBe("none");
    const refused = await getComplaintPdf(draft).then(
      () => null,
      (error: unknown) => (isApiError(error) ? error.status : null),
    );
    expect(refused).toBe(404);

    const closed = seeded("closed");
    expect((await getComplaint(closed)).pdfState).toBe("ready");
    const link = await getComplaintPdf(closed);
    expect(link.filename).toMatch(/\.pdf$/);
    expect(link.url).toMatch(/^https:/);
  });
});

describe("[CMPL-013] Download PDF on the complaint", () => {
  afterEach(reset);

  it("opens the PDF of a closed complaint in a new tab", async () => {
    signInAs("employee");
    const tab = stubNewTab();
    const user = show(seeded("closed"));

    await user.click(await screen.findByRole("button", { name: "Download PDF" }));
    await waitFor(() => {
      expect(tab.location.href).toMatch(/\/complaints\/.+\.pdf$/);
    });
    expect(tab.opener).toBeNull();
  });

  it("offers no PDF on a draft, or while the backend doesn't send pdf_state", async () => {
    signInAs("employee");
    show(seeded("draft"));
    await screen.findByRole("heading", { name: "Draft complaint" });
    expect(screen.queryByRole("button", { name: "Download PDF" })).not.toBeInTheDocument();
  });

  it("shows no button while the backend doesn't send pdf_state (before BE-031)", async () => {
    signInAs("employee");
    const id = seeded("closed");
    const response = await fetch(buildApiUrl(`/complaints/${id}`));
    const json: unknown = await response.json();
    // The same complaint, as a backend without BE-031 would send it.
    const withoutPdf = JSON.stringify(json, (key, value: unknown) =>
      key === "pdf_state" ? undefined : value,
    );
    server.use(
      http.get(
        buildApiUrl(`/complaints/${id}`),
        () => new HttpResponse(withoutPdf, { headers: { "content-type": "application/json" } }),
      ),
    );

    show(id);
    const number = mockDb.complaints.find((item) => item.id === id)?.complaint_no ?? "";
    await screen.findByRole("heading", { name: number });
    expect(screen.queryByRole("button", { name: "Download PDF" })).not.toBeInTheDocument();
  });
});
