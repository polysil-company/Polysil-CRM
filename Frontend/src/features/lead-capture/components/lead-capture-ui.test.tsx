import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { MOCK_WRONG_ENQUIRY_CODE } from "@/mocks/handlers/lead-capture";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { EnquiryPage } from "./enquiry-form";
import { QrCodes } from "./qr-codes";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
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

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

describe("[LEAD-013] QrCodes", () => {
  afterEach(reset);

  it("lists each code with its leads and whether it is on", async () => {
    signInAs("state_manager");
    show(<QrCodes />);

    const list = await screen.findByRole("list", { name: "QR codes" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(mockDb.qrCodes.length);
    expect(within(list).getByText("Switched off")).toBeInTheDocument();
    expect(within(list).getByText("31 leads")).toBeInTheDocument();
  });

  it("makes a new code, which joins the list", async () => {
    signInAs("state_manager");
    const user = show(<QrCodes />);

    await user.click(await screen.findByRole("button", { name: "New QR code" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Make the code" }));
    expect(await within(dialog).findByText(/Name it so staff recognise it/)).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Name"), "Leaflet, second print");
    await user.click(within(dialog).getByRole("button", { name: "Make the code" }));

    expect(await screen.findByText("QR code made")).toBeInTheDocument();
    expect(
      await screen.findByRole("listitem", { name: "Leaflet, second print" }),
    ).toBeInTheDocument();
  });

  it("switches a code off", async () => {
    signInAs("state_manager");
    const user = show(<QrCodes />);
    const on = mockDb.qrCodes.find((row) => row.is_active);
    if (on === undefined) throw new Error("No active code");

    await user.click(await screen.findByRole("button", { name: `Switch off ${on.label}` }));

    expect(await screen.findByText("Code switched off")).toBeInTheDocument();
    expect(mockDb.qrCodes.find((row) => row.id === on.id)?.is_active).toBe(false);
  });
});

describe("[LEAD-014] EnquiryPage", () => {
  afterEach(reset);

  async function fillDetails(user: ReturnType<typeof userEvent.setup>): Promise<void> {
    await user.type(await screen.findByLabelText("Your name"), "Kiritbhai Shah");
    await user.type(screen.getByLabelText("Mobile number"), "98765 43210");
    await user.click(screen.getByRole("radio", { name: "Drip" }));
  }

  it("takes an enquiry through a dealer's code, checked by a WhatsApp code", async () => {
    const code = mockDb.qrCodes.find((row) => row.is_active && row.territory !== null);
    if (code === undefined) throw new Error("No code with an area");
    const user = show(<EnquiryPage qr={code.code} />);

    expect(
      await screen.findByText(`Enquiry through ${code.partner?.name ?? ""}`),
    ).toBeInTheDocument();
    expect(screen.getByText("Your area comes from the code you scanned.")).toBeInTheDocument();
    await fillDetails(user);
    await user.click(screen.getByRole("button", { name: /Send me a code on WhatsApp/ }));

    const form = await screen.findByRole("form", { name: "Enter the code from WhatsApp" });
    expect(within(form).getByText("+91 98765 43210")).toBeInTheDocument();
    await user.type(within(form).getByLabelText("6-digit code"), "482913");

    const done = await screen.findByRole("region", { name: "Your enquiry number" });
    const lead = mockDb.leads[0];
    expect(within(done).getByText(lead?.inquiry_no ?? "missing")).toBeInTheDocument();
    expect(lead).toMatchObject({ source: "qr_code", territory: { id: code.territory?.id } });
  });

  it("asks for the district when no code chose the area", async () => {
    const user = show(<EnquiryPage qr={null} />);
    await fillDetails(user);
    await user.click(screen.getByRole("button", { name: /Send me a code on WhatsApp/ }));

    expect(await screen.findByText("Choose your district.")).toBeInTheDocument();
  });

  it("says a wrong code doesn't match, and keeps the farmer on the code step", async () => {
    const code = mockDb.qrCodes.find((row) => row.is_active && row.territory !== null);
    if (code === undefined) throw new Error("No code with an area");
    const user = show(<EnquiryPage qr={code.code} />);
    await fillDetails(user);
    await user.click(screen.getByRole("button", { name: /Send me a code on WhatsApp/ }));
    const form = await screen.findByRole("form", { name: "Enter the code from WhatsApp" });
    await user.type(within(form).getByLabelText("6-digit code"), MOCK_WRONG_ENQUIRY_CODE);

    expect(await within(form).findByText(/doesn't match, or it has expired/)).toBeInTheDocument();
  });

  it("opens the plain form when the scanned code is no longer in use", async () => {
    const off = mockDb.qrCodes.find((row) => !row.is_active);
    if (off === undefined) throw new Error("No switched-off code");
    show(<EnquiryPage qr={off.code} />);

    expect(await screen.findByText(/isn't in use any more/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText(/^Enquiry through/)).not.toBeInTheDocument();
    });
  });
});
