import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  checkApplicantCode,
  getApplicantView,
  patchApplicantFields,
  sendApplicantCode,
  submitApplicantApplication,
  uploadApplicantDocument,
} from "@/features/dealer-applications/api/dealer-apply.api";
import { MOCK_OTP_CODE } from "@/lib/dev/mock-settings";
import { resetMockDb } from "@/mocks/db";
import { mockDealerApplications } from "@/mocks/handlers/dealer-applications";
import { renderWithProviders } from "@/test/render";

import { DealerApplyPage } from "./dealer-apply-page";

/** A whole journey: verify, save, upload. */
const JOURNEY = { timeout: 15_000 };

function tokenOf(status: string): string {
  const application = mockDealerApplications().find((item) => item.status === status);
  if (application === undefined) throw new Error(`No ${status} application`);
  return application.token;
}

function pdf(name: string): File {
  return new File(["%PDF-1.4"], name, { type: "application/pdf" });
}

async function verify(token: string): Promise<string> {
  await sendApplicantCode(token);
  return checkApplicantCode(token, MOCK_OTP_CODE);
}

describe("[CHNL-008] The applicant's calls", () => {
  beforeEach(resetMockDb);
  afterEach(resetMockDb);

  it("shows only the outline until the mobile is verified, then every field", async () => {
    const token = tokenOf("draft");
    const outline = await getApplicantView({ token, session: null });
    expect(outline).toMatchObject({ verified: false, fields: null, documents: [] });
    expect(outline.mobileMasked).toMatch(/^\+91 xxxxxx\d{4}$/);

    await sendApplicantCode(token);
    await expect(checkApplicantCode(token, "000000")).rejects.toMatchObject({
      status: 422,
      code: "invalid_code",
    });
    const session = await checkApplicantCode(token, MOCK_OTP_CODE);
    const full = await getApplicantView({ token, session });
    expect(full.verified).toBe(true);
    expect(full.fields?.firmName).toBe(outline.firmName);
  });

  it("refuses a write without a session, and submits once nothing is missing", async () => {
    const token = tokenOf("draft");
    await expect(
      patchApplicantFields({ token, session: null }, { pan: "AAACP1234F" }),
    ).rejects.toMatchObject({ status: 403, code: "no_session" });

    const applicant = { token, session: await verify(token) };
    await expect(submitApplicantApplication(applicant)).rejects.toMatchObject({
      status: 422,
      code: "application_incomplete",
    });
    await patchApplicantFields(applicant, {
      firm_type: "proprietorship",
      gst_registered: false,
      pan: "AAACP1234F",
      address: "Shop 2, Main Bazaar",
      pincode: "360001",
      bank_account_name: "Shree Krishna Krishi Kendra",
      bank_account_no: "001234567890",
      bank_ifsc: "SBIN0001234",
    });
    await uploadApplicantDocument(applicant, {
      docType: "pan_card",
      name: null,
      file: pdf("pan.pdf"),
    });
    await uploadApplicantDocument(applicant, {
      docType: "cancelled_cheque",
      name: null,
      file: pdf("cheque.pdf"),
    });
    await submitApplicantApplication(applicant);
    expect((await getApplicantView(applicant)).status).toBe("submitted");
  });
});

describe("[CHNL-008] DealerApplyPage", () => {
  beforeEach(resetMockDb);
  afterEach(resetMockDb);

  function show(token: string): ReturnType<typeof userEvent.setup> {
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <DealerApplyPage token={token} />
        <Toaster />
      </>,
    );
    return user;
  }

  it(
    "verifies the mobile with a WhatsApp code, then saves the details and uploads",
    JOURNEY,
    async () => {
      const user = show(tokenOf("draft"));

      await user.click(await screen.findByRole("button", { name: "Send the code on WhatsApp" }));
      const code = await screen.findByLabelText("6-digit code");
      await user.type(code, "000000");
      await user.click(screen.getByRole("button", { name: "Verify" }));
      expect(
        await screen.findByText("That code didn't work. Check it, or ask for a new one."),
      ).toBeInTheDocument();
      await user.type(screen.getByLabelText("6-digit code"), MOCK_OTP_CODE);
      // the button says "Not verified" for a moment after a wrong code
      await user.click(await screen.findByRole("button", { name: "Verify" }, { timeout: 4000 }));

      const form = await screen.findByRole("form", { name: "Your details" });
      expect(screen.getByRole("button", { name: "Submit the application" })).toBeDisabled();
      await user.type(within(form).getByRole("textbox", { name: "PAN" }), "AAACP1234F");
      await user.click(within(form).getByRole("button", { name: "Save" }));
      expect(await screen.findByText("Saved", { selector: "[data-title]" })).toBeVisible();

      const upload = screen.getByRole("form", { name: "Upload a document" });
      await user.upload(within(upload).getByLabelText("File"), pdf("pan.pdf"));
      await user.click(within(upload).getByRole("button", { name: "Upload" }));
      const list = await screen.findByRole("list", { name: "Uploaded documents" });
      expect(within(list).getByText("pan.pdf")).toBeInTheDocument();
      await waitFor(() => {
        expect(screen.queryByText(/PAN card \(document\)/)).not.toBeInTheDocument();
      });
    },
  );

  it("shows what to fix on a returned application, once verified", async () => {
    const user = show(tokenOf("returned"));

    await user.click(await screen.findByRole("button", { name: "Send the code on WhatsApp" }));
    await user.type(await screen.findByLabelText("6-digit code"), MOCK_OTP_CODE);
    await user.click(screen.getByRole("button", { name: "Verify" }));

    expect(await screen.findByText("Polysil sent your application back")).toBeInTheDocument();
    expect(screen.getByText(/The cancelled cheque is unreadable/)).toBeInTheDocument();
  });

  it("says a link that no longer works, and a submitted one, in words", async () => {
    show("apply-nothing-here");
    expect(await screen.findByText("This link doesn't work any more")).toBeInTheDocument();
  });

  it("says a submitted application waits on Polysil", async () => {
    show(tokenOf("submitted"));
    expect(await screen.findByText("Submitted, we will be in touch")).toBeInTheDocument();
  });
});
