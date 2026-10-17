import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { checkImport, commitImport, uploadImport } from "@/features/imports/api/imports.api";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { MOCK_TERRITORIES } from "@/mocks/data/territories";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";

import {
  createPartner,
  getPartner,
  listPartners,
  lookupGstin,
  patchPartner,
  searchParents,
  setPartnerOpen,
} from "./partners.api";
import type { CreatePartnerRequest, PartnerListParams } from "./partners.schemas";

let keys = 0;
function key(): string {
  keys += 1;
  return `partners-test-${String(keys)}`;
}

const ALL: PartnerListParams = { q: "", type: null, parentId: null, active: null, cursor: null };

function idOf(name: string): string {
  const partner = mockDb.partners.find((item) => item.name === name);
  if (partner === undefined) throw new Error(`No ${name}`);
  return partner.id;
}

function district(name: string): string {
  const found = MOCK_TERRITORIES.find((item) => item.level === "district" && item.name === name);
  if (found === undefined) throw new Error(`No ${name}`);
  return found.id;
}

async function refusal(call: Promise<unknown>): Promise<{
  status: number;
  fields: Readonly<Record<string, string>> | null;
}> {
  try {
    await call;
  } catch (error) {
    if (isApiError(error)) return { status: error.status ?? 0, fields: readFieldErrors(error) };
    throw error;
  }
  throw new Error("Expected the call to be refused");
}

function dealer(overrides: Partial<CreatePartnerRequest> = {}): CreatePartnerRequest {
  return {
    parent_id: idOf("Saurashtra Agro Distributors"),
    partner_type: "dealer",
    code: "DL-NEW-1",
    name: "Gondal Krishi Seva",
    territory_id: district("Rajkot"),
    contact_name: "Ketan Shah",
    mobile: "+91 98765 01234",
    email: null,
    address: null,
    gstin: null,
    pan: null,
    is_gst_registered: false,
    credit_limit: "150000.00",
    payment_terms_days: 30,
    ...overrides,
  };
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

describe("[CHNL-001] Channel partners — list and detail", () => {
  beforeEach(reset);
  afterEach(reset);

  it("lists every partner newest first with the total, and filters by type, parent and status", async () => {
    const page = await listPartners(ALL);
    expect(page.total).toBe(9);
    expect(page.items[0]?.name).toBe("Babra Farm Supplies");

    const dealers = await listPartners({ ...ALL, type: "dealer" });
    expect(dealers.items.every((partner) => partner.type === "dealer")).toBe(true);

    const under = await listPartners({ ...ALL, parentId: idOf("Saurashtra Agro Distributors") });
    expect(under.items.map((partner) => partner.name).sort()).toEqual([
      "Ambika Krishi Kendra",
      "Khodiyar Irrigation",
      "Shree Ganesh Agro Agency",
    ]);

    const closed = await listPartners({ ...ALL, active: false });
    expect(closed.items.map((partner) => partner.name)).toEqual(["Balagam Krishi Seva"]);

    const searched = await listPartners({ ...ALL, q: "cp-001" });
    expect(searched.items.map((partner) => partner.code)).toEqual(["CP-001"]);
  });

  it("reads one partner, with credit terms for whoever may edit partners only", async () => {
    const id = idOf("Saurashtra Agro Distributors");
    const partner = await getPartner(id);
    expect(partner).toMatchObject({
      code: "CP-001",
      type: "distributor",
      parent: null,
      territory: { name: "Rajkot", level: "district" },
      creditLimit: "500000.00",
      paymentTermsDays: 45,
      users: 1,
    });

    writeMockRole("employee");
    expect(await getPartner(id)).toMatchObject({ creditLimit: null, paymentTermsDays: null });
  });

  it("offers only open partners of the type one up as a parent", async () => {
    const distributors = await searchParents("distributor", "");
    expect(distributors.map((partner) => partner.name).sort()).toEqual([
      "Saurashtra Agro Distributors",
      "Sorath Agri Distributors",
    ]);
    expect((await searchParents("dealer", "patel")).map((partner) => partner.name)).toEqual([
      "Patel Agro Traders",
    ]);
  });
});

describe("[CHNL-002] Add a partner", () => {
  beforeEach(reset);
  afterEach(reset);

  it("adds a dealer under its distributor, its mobile as the backend stores it", async () => {
    const made = await createPartner({ body: dealer(), idempotencyKey: key() });
    expect(made).toMatchObject({
      code: "DL-NEW-1",
      type: "dealer",
      parent: { name: "Saurashtra Agro Distributors", type: "distributor" },
      mobile: "919876501234",
      creditLimit: "150000.00",
      active: true,
      users: 0,
    });
    expect((await listPartners(ALL)).items[0]?.name).toBe("Gondal Krishi Seva");
  });

  it("refuses a used code, the wrong parent, a GST-registered partner without a GSTIN, on the field", async () => {
    expect(
      await refusal(createPartner({ body: dealer({ code: "cp-003" }), idempotencyKey: key() })),
    ).toEqual({ status: 422, fields: { code: "already in use" } });

    const underDealer = await refusal(
      createPartner({
        body: dealer({ parent_id: idOf("Patel Agro Traders") }),
        idempotencyKey: key(),
      }),
    );
    expect(underDealer.fields?.partner_type).toMatch(/^wrong type for this parent/);

    expect(
      await refusal(
        createPartner({
          body: dealer({ is_gst_registered: true }),
          idempotencyKey: key(),
        }),
      ),
    ).toEqual({ status: 422, fields: { gstin: "required when GST registered" } });

    expect(
      await refusal(
        createPartner({ body: dealer({ gstin: "24ABC", pan: "12" }), idempotencyKey: key() }),
      ),
    ).toEqual({ status: 422, fields: { gstin: "not a GSTIN", pan: "not a PAN" } });
  });

  it("is refused to someone without partners.create", async () => {
    writeMockRole("employee");
    expect((await refusal(createPartner({ body: dealer(), idempotencyKey: key() }))).status).toBe(
      403,
    );
  });
});

describe("[CHNL-003] Correct a partner", () => {
  beforeEach(reset);
  afterEach(reset);

  it("changes only what is sent, clears an optional field with null, and renames it on its dealers", async () => {
    const id = idOf("Saurashtra Agro Distributors");
    const saved = await patchPartner({
      partnerId: id,
      body: { name: "Saurashtra Agro Distributors LLP", email: null, payment_terms_days: 60 },
      idempotencyKey: key(),
    });
    expect(saved).toMatchObject({
      name: "Saurashtra Agro Distributors LLP",
      email: null,
      paymentTermsDays: 60,
      code: "CP-001",
    });
    const child = await getPartner(idOf("Khodiyar Irrigation"));
    expect(child.parent?.name).toBe("Saurashtra Agro Distributors LLP");
  });

  it("refuses a change that changes nothing", async () => {
    const id = idOf("Patel Agro Traders");
    expect(await refusal(patchPartner({ partnerId: id, body: {}, idempotencyKey: key() }))).toEqual(
      { status: 422, fields: { body: "nothing to change" } },
    );
  });
});

describe("[CHNL-004] Close or reopen a partner", () => {
  beforeEach(reset);
  afterEach(reset);

  it("closes a partner and deactivates its users; reopening leaves them inactive", async () => {
    const id = idOf("Saurashtra Agro Distributors");
    const closed = await setPartnerOpen({ partnerId: id, open: false, idempotencyKey: key() });
    expect(closed.partner).toMatchObject({ active: false, users: 0 });
    expect(closed.usersInactive).toBe(1);
    expect(mockDb.users.find((user) => user.partner?.id === id)?.is_active).toBe(false);

    const reopened = await setPartnerOpen({ partnerId: id, open: true, idempotencyKey: key() });
    expect(reopened.partner.active).toBe(true);
    expect(reopened.usersInactive).toBe(1);
  });

  it("is refused to a partner's own users", async () => {
    writeMockRole("dealer");
    const id = idOf("Patel Agro Traders");
    expect(
      (await refusal(setPartnerOpen({ partnerId: id, open: false, idempotencyKey: key() }))).status,
    ).toBe(403);
  });
});

const PARTNERS_CSV = [
  "Type,Dealer Code,Firm Name,State,District,Under,Owner,Mobile",
  "Distributor,D-NEW-01,Mehsana Agro Distributors,Gujarat,Rajkot,,Mahesh Patel,98250 11223",
  "Dealer,DL-NEW-01,Gondal Krishi Seva,GJ,Rajkot,D-NEW-01,Ketan Shah,+91 98765 01234",
  "Dealer,DL-NEW-02,Jasdan Irrigation,Gujarat,Nowhere,D-NEW-01,,",
  "Sub-dealer,SD-NEW-01,Virpur Seeds,Gujarat,,CP-001,,",
  "Dealer,CP-002,Repeat Code Traders,Gujarat,,CP-001,,",
].join("\n");

describe("[CHNL-005] Import partners from Excel", () => {
  beforeEach(reset);
  afterEach(reset);

  it("checks each row as the backend does, then adds the good ones under the parents they name", async () => {
    const batch = await uploadImport({
      kind: "partners",
      file: new File([PARTNERS_CSV], "dealers.csv", { type: "text/csv" }),
      idempotencyKey: key(),
    });
    expect(batch.suggestedMapping).toMatchObject({
      partner_type: 0,
      code: 1,
      name: 2,
      state: 3,
      district: 4,
      parent_code: 5,
      contact_name: 6,
      mobile: 7,
    });

    const check = await checkImport({
      batchId: batch.id,
      body: { mapping: batch.suggestedMapping },
      idempotencyKey: key(),
    });
    expect(check).toMatchObject({ total: 5, ok: 2, errors: 3 });
    expect(check.errorRows).toEqual([
      { row: 4, errors: { district: "no district 'Nowhere' in Gujarat" } },
      {
        row: 5,
        errors: {
          parent_code: "wrong type for this parent: the order is distributor > dealer > sub-dealer",
        },
      },
      { row: 6, errors: { code: "CP-002 is already in use" } },
    ]);
    expect(check.preview[1]?.values).toMatchObject({
      code: "DL-NEW-01",
      territory: "Rajkot, Gujarat",
      mobile: "919876501234",
    });

    const result = await commitImport({
      batchId: batch.id,
      skipInvalid: true,
      idempotencyKey: key(),
    });
    expect(result).toEqual({ created: 2, skipped: 3 });
    const added = await listPartners({ ...ALL, q: "Gondal" });
    expect(added.items[0]?.parent?.name).toBe("Mehsana Agro Distributors");
  });
});

describe("[CHNL-006] lookupGstin", () => {
  afterEach(() => {
    writeMockRole("admin");
  });

  it("reads a GST record the backend found, trimming empty names to null", async () => {
    server.use(
      http.get(buildApiUrl("/gstin/:gstin"), () =>
        HttpResponse.json({
          data: {
            gstin: "24AAACP1234F1Z5",
            valid: true,
            reason: null,
            state_code: "24",
            pan: "AAACP1234F",
            lookup: "found",
            legal_name: "Patel Agro Irrigation Private Limited",
            trade_name: " ",
            address: null,
            status: "Active",
          },
        }),
      ),
    );

    expect(await lookupGstin("24AAACP1234F1Z5")).toEqual({
      gstin: "24AAACP1234F1Z5",
      valid: true,
      reason: null,
      pan: "AAACP1234F",
      lookup: "found",
      legalName: "Patel Agro Irrigation Private Limited",
      tradeName: null,
      address: null,
      status: "Active",
    });
  });

  it("answers unavailable for a GSTIN the mock has no record of, as the backend without a provider", async () => {
    const lookup = await lookupGstin("24ABCDE1234F1Z5");
    expect(lookup).toMatchObject({ valid: true, lookup: "unavailable", legalName: null });
  });

  it("is refused to partner users", async () => {
    writeMockRole("dealer");
    await expect(lookupGstin("24AAACP1234F1Z5")).rejects.toSatisfy(
      (error) => isApiError(error) && error.status === 403,
    );
  });
});
