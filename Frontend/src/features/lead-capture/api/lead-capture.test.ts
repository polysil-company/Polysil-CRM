import { afterEach, describe, expect, it } from "vitest";

import { writeMockRole } from "@/lib/dev/mock-settings";
import { MOCK_PARTNERS } from "@/mocks/data/reference";
import { mockDb, resetMockDb } from "@/mocks/db";
import { MOCK_WRONG_ENQUIRY_CODE } from "@/mocks/handlers/lead-capture";

import {
  createQrCode,
  getPublicLeadForm,
  listPublicTerritories,
  listQrCodes,
  patchQrCode,
  sendEnquiryCode,
  submitEnquiry,
} from "./lead-capture.api";
import type { PublicLeadRequest } from "./lead-capture.schemas";

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

describe("[LEAD-013] QR codes", () => {
  afterEach(reset);

  it("makes a code that opens the enquiry page, then renames and switches it off", async () => {
    writeMockRole("state_manager");
    const made = await createQrCode({
      body: {
        label: "Stall at the fair",
        campaign: null,
        partner_id: MOCK_PARTNERS[0]?.id ?? null,
        territory_id: null,
      },
      idempotencyKey: "q-1",
    });
    expect(made).toMatchObject({ isActive: true, leadCount: 0 });
    expect(made.url).toMatch(/\/enquiry\?qr=[2-9A-Z]{6}$/);
    expect((await listQrCodes())[0]?.id).toBe(made.id);

    const off = await patchQrCode({
      qrId: made.id,
      body: { label: "Stall, day two", is_active: false },
      idempotencyKey: "q-2",
    });
    expect(off).toMatchObject({ label: "Stall, day two", isActive: false, code: made.code });
  });

  it("refuses a dealer that isn't found", async () => {
    writeMockRole("state_manager");
    await expect(
      createQrCode({
        body: { label: "X", campaign: null, partner_id: "nope", territory_id: null },
        idempotencyKey: "q-3",
      }),
    ).rejects.toMatchObject({ status: 422, details: { fields: { partner_id: "not found" } } });
  });
});

describe("[LEAD-014] the public enquiry", () => {
  afterEach(reset);

  async function request(qr: string | null): Promise<PublicLeadRequest> {
    const form = await getPublicLeadForm(qr);
    const state = form.states[0];
    if (state === undefined) throw new Error("No state");
    const district = (await listPublicTerritories(state.id))[0];
    if (district === undefined) throw new Error("No district");
    return {
      mobile: "98765 43210",
      code: "482913",
      farmer_name: "Kiritbhai Shah",
      territory_id: district.id,
      village: "Gondal",
      mis_system: form.systems[0]?.code ?? "drip",
      inquiry_type: "commercial",
      note: null,
      qr,
    };
  }

  it("names the code's dealer, then makes a lead credited to it once the code matches", async () => {
    const code = mockDb.qrCodes.find((row) => row.is_active && row.partner !== null);
    if (code === undefined) throw new Error("No active dealer code");
    const form = await getPublicLeadForm(code.code);
    expect(form.qr?.label).toBe(code.partner?.name);

    const sent = await sendEnquiryCode("98765 43210");
    expect(sent).toMatchObject({ expiresIn: 600, resendAfter: 60 });
    const before = code.lead_count;
    const result = await submitEnquiry(await request(code.code));
    expect(result.created).toBe(true);
    expect(mockDb.leads[0]).toMatchObject({
      inquiry_no: result.inquiryNo,
      source: "qr_code",
      assigned_partner: { id: code.partner?.id },
    });
    expect(code.lead_count).toBe(before + 1);

    // The same mobile again today answers the first number.
    const again = await submitEnquiry(await request(code.code));
    expect(again).toEqual({ inquiryNo: result.inquiryNo, created: false });
  });

  it("refuses a wrong code, and a code no longer in use", async () => {
    await sendEnquiryCode("98765 43210");
    await expect(
      submitEnquiry({ ...(await request(null)), code: MOCK_WRONG_ENQUIRY_CODE }),
    ).rejects.toMatchObject({ code: "invalid_code" });

    const off = mockDb.qrCodes.find((row) => !row.is_active);
    if (off === undefined) throw new Error("No switched-off code");
    await expect(getPublicLeadForm(off.code)).rejects.toMatchObject({ status: 404 });
  });
});
