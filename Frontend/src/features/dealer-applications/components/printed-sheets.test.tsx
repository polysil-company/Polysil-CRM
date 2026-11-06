import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  downloadBlankApplicationForm,
  downloadDealerApplicationPdf,
} from "@/features/dealer-applications/api/dealer-applications.api";
import {
  checkApplicantCode,
  downloadApplicantPdf,
  sendApplicantCode,
} from "@/features/dealer-applications/api/dealer-apply.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { MOCK_OTP_CODE, writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { mockDealerApplications } from "@/mocks/handlers/dealer-applications";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { DealerApplicationDetail } from "./dealer-application-detail";
import { DealerApplicationsList } from "./dealer-applications-list";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), notFound: vi.fn() }));

const saveFile = vi.fn();
vi.mock("@/lib/api/save-file", () => ({
  saveFile: (...args: unknown[]) => {
    saveFile(...args);
  },
}));

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
  saveFile.mockReset();
}

function seeded(status: string): { id: string; token: string } {
  const application = mockDealerApplications().find((item) => item.status === status);
  if (application === undefined) throw new Error(`No ${status} application`);
  return { id: application.id, token: application.token };
}

describe("[CHNL-007] The printed sheets (FS-071), through the API", () => {
  beforeEach(reset);
  afterEach(reset);

  it("fetches the blank form for each type, and an application's own", async () => {
    signInAs("district_manager");
    const blank = await downloadBlankApplicationForm("distributor");
    expect(blank.filename).toBe("distributor-application-form.pdf");
    expect(blank.blob.type).toContain("application/pdf");

    const filled = await downloadDealerApplicationPdf(seeded("submitted").id);
    expect(filled.filename).toBe("application-patel-agro.pdf");
  });

  it("gives the applicant their sheet only once their mobile is verified", async () => {
    const { token } = seeded("draft");
    await expect(downloadApplicantPdf({ token, session: null })).rejects.toMatchObject({
      status: 403,
      code: "no_session",
    });
    await sendApplicantCode(token);
    const session = await checkApplicantCode(token, MOCK_OTP_CODE);
    const sheet = await downloadApplicantPdf({ token, session });
    expect(sheet.filename).toBe("my-application.pdf");
  });
});

describe("[CHNL-007] The printed sheets on the screens (FS-071)", () => {
  beforeEach(reset);
  afterEach(reset);

  it("saves an application's sheet, and says when the PDF maker is busy", async () => {
    signInAs("district_manager");
    const user = show(<DealerApplicationDetail applicationId={seeded("submitted").id} />);

    await user.click(await screen.findByRole("button", { name: "Download PDF" }));
    await vi.waitFor(() => {
      expect(saveFile).toHaveBeenCalledWith(
        expect.objectContaining({ filename: "application-patel-agro.pdf" }),
        "application.pdf",
      );
    });

    server.use(
      http.get(buildApiUrl("/dealer-applications/:applicationId/pdf"), () =>
        HttpResponse.json(
          { error: { code: "busy", message: "Other PDFs are being made." } },
          { status: 503 },
        ),
      ),
    );
    await user.click(screen.getByRole("button", { name: /Download PDF|Downloaded/ }));
    expect(await screen.findByText("The PDF maker is busy")).toBeInTheDocument();
  });

  it("offers a blank form for each type from the list", async () => {
    signInAs("district_manager");
    const user = show(<DealerApplicationsList />);

    await user.click(await screen.findByRole("button", { name: "Blank form" }));
    await user.click(await screen.findByRole("menuitem", { name: "For a new distributor" }));
    await vi.waitFor(() => {
      expect(saveFile).toHaveBeenCalledWith(
        expect.objectContaining({ filename: "distributor-application-form.pdf" }),
        "application-form.pdf",
      );
    });
  });
});
