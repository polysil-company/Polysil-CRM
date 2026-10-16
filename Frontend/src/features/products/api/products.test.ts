import { afterEach, describe, expect, it } from "vitest";

import { isApiError } from "@/lib/api/errors";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockDb, resetMockDb } from "@/mocks/db";

import {
  assignHsn,
  closePriceList,
  createProduct,
  getHsnHistory,
  listCatalogueFacets,
  listPriceListItems,
  listProducts,
  patchProduct,
  publishPriceList,
  readAllRates,
  replaceRates,
  setTaxRate,
} from "./products.api";
import type { CreateProductRequest, ProductListParams } from "./products.schemas";

let keys = 0;
function key(): string {
  keys += 1;
  return `products-test-${String(keys)}`;
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

const ALL: ProductListParams = { q: "", category: null, quotationCategory: null, active: true };

const NEW_PRODUCT: CreateProductRequest = {
  description: "ONLINE DRIPPER 8 LPH",
  product_category: "DRIP COMPONENTS",
  quotation_category: "field",
  uom: "NOS",
  item_code: null,
  mrp: "6.50",
  pack_multiple: null,
  is_subsidy_eligible: true,
};

function listNamed(name: string): string {
  const list = mockDb.priceLists.find((item) => item.name === name);
  if (list === undefined) throw new Error(`No list ${name}`);
  return list.id;
}

function productNamed(description: string): string {
  const product = mockDb.products.find((item) => item.description === description);
  if (product === undefined) throw new Error(`No product ${description}`);
  return product.id;
}

describe("[MSTR-004] product catalogue", () => {
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
  });

  it("lists active products a page at a time, with each one's stand-in figures", async () => {
    writeMockRole("admin");
    const page = await listProducts({ ...ALL, page: 1 });

    expect(page.total).toBe(9);
    expect(page.items.some((product) => !product.active)).toBe(false);
    expect(page.items.find((product) => product.description === "PVC ELBOW 90 MM")).toMatchObject({
      quotationCategory: "both",
      provisional: ["mrp", "pack_multiple"],
    });
  });

  it("searches by description, and lists switched-off products only when asked", async () => {
    writeMockRole("admin");
    const found = await listProducts({ ...ALL, q: "dripper", page: 1 });
    const off = await listProducts({ ...ALL, active: false, page: 1 });

    expect(found.items.map((product) => product.description)).toEqual(["INLINE DRIPPER 4 LPH"]);
    expect(off.items.map((product) => product.description)).toEqual([
      "BALL VALVE 2 INCH (OLD MODEL)",
    ]);
  });

  it("offers the categories and units in use, switched-off products included", async () => {
    writeMockRole("admin");
    const facets = await listCatalogueFacets();

    expect(facets.categories).toContain("PVC FITTINGS");
    expect(facets.categories).toContain("Marketing");
    expect(facets.units).toContainEqual({ code: "MTR", decimals: 2 });
  });

  it("adds a product, and refuses a description already in the catalogue", async () => {
    writeMockRole("admin");
    const added = await createProduct({ body: NEW_PRODUCT, idempotencyKey: key() });
    const again = await refusal(createProduct({ body: NEW_PRODUCT, idempotencyKey: key() }));

    expect(added).toMatchObject({
      description: "ONLINE DRIPPER 8 LPH",
      hsnCode: null,
      active: true,
    });
    expect(again).toEqual({ status: 409, code: "duplicate_description" });
  });

  it("confirms a stand-in figure once it is set, and switches a product off", async () => {
    writeMockRole("admin");
    const elbow = productNamed("PVC ELBOW 90 MM");
    const priced = await patchProduct({
      productId: elbow,
      body: { mrp: "215.50" },
      idempotencyKey: key(),
    });
    const off = await patchProduct({
      productId: elbow,
      body: { is_active: false },
      idempotencyKey: key(),
    });

    expect(priced).toMatchObject({ mrp: "215.50", provisional: ["pack_multiple"] });
    expect(off.active).toBe(false);
  });

  it("lets everyone read the catalogue, but only Admin-Sales change it", async () => {
    writeMockRole("employee");

    await expect(listProducts({ ...ALL, page: 1 })).resolves.toMatchObject({ total: 9 });
    expect(
      await refusal(createProduct({ body: NEW_PRODUCT, idempotencyKey: key() })),
    ).toMatchObject({
      status: 403,
    });
  });
});

describe("[MSTR-005] HSN codes and GST rates", () => {
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
  });

  it("classifies a product from a date, closing the heading in force", async () => {
    writeMockRole("admin");
    const elbow = productNamed("PVC ELBOW 90 MM");
    const history = await assignHsn({
      productId: elbow,
      hsnCode: "3925",
      from: "2026-11-01",
      idempotencyKey: key(),
    });

    expect(history).toEqual([
      expect.objectContaining({ hsnCode: "3925", from: "2026-11-01", to: null }),
      expect.objectContaining({ hsnCode: "3917", from: "2026-04-01", to: "2026-11-01" }),
    ]);
    await expect(getHsnHistory(elbow)).resolves.toHaveLength(2);
  });

  it("refuses a new heading on the start date of the one in force", async () => {
    writeMockRole("admin");
    const elbow = productNamed("PVC ELBOW 90 MM");

    expect(
      await refusal(
        assignHsn({ productId: elbow, hsnCode: "3925", from: "2026-04-01", idempotencyKey: key() }),
      ),
    ).toEqual({ status: 409, code: "hsn_same_start_date" });
  });

  it("sets a slab per code from a date, and refuses one the Council doesn't use", async () => {
    writeMockRole("admin");
    const rates = await setTaxRate({
      hsnCode: "3917",
      rate: "18",
      from: "2026-11-01",
      idempotencyKey: key(),
    });

    expect(rates.items).toContainEqual(
      expect.objectContaining({ hsnCode: "3917", from: "2026-11-01", to: null }),
    );
    expect(
      await refusal(
        setTaxRate({ hsnCode: "3917", rate: "15", from: "2026-12-01", idempotencyKey: key() }),
      ),
    ).toMatchObject({ status: 422 });
  });
});

describe("[MSTR-006] price lists", () => {
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
  });

  it("reads a list's rate sheet with the active products it has no rate for", async () => {
    writeMockRole("admin");
    const sheet = await listPriceListItems({
      listId: listNamed("Gujarat dealers, November"),
      q: "",
      unpriced: true,
      page: 1,
    });

    expect(sheet.unpriced).toBe(7);
    expect(sheet.items.every((item) => item.rate === null)).toBe(true);
  });

  it("replaces a draft's rates, keeping the others when they are read first", async () => {
    writeMockRole("admin");
    const listId = listNamed("Gujarat dealers, November");
    const rates = await readAllRates(listId);
    rates.set(productNamed("PVC ELBOW 90 MM"), "180.5");
    const saved = await replaceRates({ listId, rates, idempotencyKey: key() });

    expect(saved.unpriced).toBe(6);
    await expect(readAllRates(listId)).resolves.toHaveProperty("size", 3);
  });

  it("refuses a rate with more than two decimals instead of rounding it", async () => {
    writeMockRole("admin");
    const listId = listNamed("Gujarat dealers, November");
    const rates = new Map([[productNamed("PVC ELBOW 90 MM"), "180.555"]]);

    expect(await refusal(replaceRates({ listId, rates, idempotencyKey: key() }))).toMatchObject({
      status: 422,
    });
  });

  it("never changes a published list's rates", async () => {
    writeMockRole("admin");
    const listId = listNamed("GJ 2026-27");

    expect(
      await refusal(replaceRates({ listId, rates: new Map(), idempotencyKey: key() })),
    ).toEqual({
      status: 409,
      code: "price_list_published",
    });
  });

  it("publishes a list missing rates only when that is meant", async () => {
    writeMockRole("admin");
    const listId = listNamed("Gujarat dealers, November");

    expect(
      await refusal(publishPriceList({ listId, allowUnpriced: false, idempotencyKey: key() })),
    ).toEqual({ status: 409, code: "price_list_unpriced" });
    await expect(
      publishPriceList({ listId, allowUnpriced: true, idempotencyKey: key() }),
    ).resolves.toEqual({ closedPredecessorId: null });
  });

  it("closes a published list going forward only", async () => {
    writeMockRole("admin");
    const listId = listNamed("GJ 2026-27");

    expect(
      await refusal(closePriceList({ listId, to: "2026-05-01", idempotencyKey: key() })),
    ).toMatchObject({ status: 422 });
    await expect(
      closePriceList({ listId, to: "2027-04-01", idempotencyKey: key() }),
    ).resolves.toMatchObject({ to: "2027-04-01" });
  });

  it("lets everyone read price lists, but only Admin-Sales change them", async () => {
    writeMockRole("employee");
    const listId = listNamed("Gujarat dealers, November");

    await expect(readAllRates(listId)).resolves.toHaveProperty("size", 2);
    expect(
      await refusal(publishPriceList({ listId, allowUnpriced: true, idempotencyKey: key() })),
    ).toMatchObject({ status: 403 });
  });
});
