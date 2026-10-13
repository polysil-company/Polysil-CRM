import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { PriceListSheet } from "./price-list-sheet";
import { ProductMaster } from "./product-master";

const push = vi.fn();
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push, back: vi.fn() }),
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function listNamed(name: string): string {
  const list = mockDb.priceLists.find((item) => item.name === name);
  if (list === undefined) throw new Error(`No list ${name}`);
  return list.id;
}

function show(ui: React.ReactElement, searchParams = ""): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      {ui}
      <Toaster />
    </>,
    { searchParams },
  );
  return user;
}

describe("[MSTR-004] ProductMaster catalogue", () => {
  beforeEach(() => {
    signInAs("admin");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
    push.mockReset();
  });

  it("lists active products with their stand-ins and missing HSN codes", async () => {
    show(<ProductMaster />);

    const list = await screen.findByRole("list", { name: "Products" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(9);
    expect(screen.getByText("9 products, active.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "PVC ELBOW 90 MM, has stand-in figures" }),
    ).toBeInTheDocument();
    expect(within(list).getByText("No HSN")).toBeInTheDocument();
  });

  it("explains an empty search and offers to reset it", async () => {
    const user = show(<ProductMaster />, "?q=nothing-like-this");

    expect(await screen.findByText("No products match these filters")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Reset filters" })[0] ?? document.body);
    expect(await screen.findByRole("list", { name: "Products" })).toBeInTheDocument();
  });

  it("says what is missing, then refuses a description already in use", async () => {
    const user = show(<ProductMaster />);
    await user.click(await screen.findByRole("button", { name: "New product" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Add the product" }));

    expect(
      within(dialog).getByText("Describe it as it prints on a quotation."),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Choose its category.")).toBeInTheDocument();
    expect(within(dialog).getByText("Choose its unit.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Description"), "INLINE DRIPPER 4 LPH");
    await user.click(within(dialog).getByRole("combobox", { name: "Category" }));
    await user.click(await screen.findByRole("option", { name: "DRIP COMPONENTS" }));
    await user.click(within(dialog).getByRole("combobox", { name: "Unit" }));
    await user.click(await screen.findByRole("option", { name: /^NOS/ }));
    await user.click(within(dialog).getByRole("button", { name: "Add the product" }));

    expect(
      await within(dialog).findByText("Another product already has this description."),
    ).toBeInTheDocument();
  });

  it("adds a product to the catalogue", async () => {
    const user = show(<ProductMaster />);
    await user.click(await screen.findByRole("button", { name: "New product" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Description"), "ONLINE DRIPPER 8 LPH");
    await user.click(within(dialog).getByRole("combobox", { name: "Category" }));
    await user.click(await screen.findByRole("option", { name: "DRIP COMPONENTS" }));
    await user.click(within(dialog).getByRole("combobox", { name: "Unit" }));
    await user.click(await screen.findByRole("option", { name: /^NOS/ }));
    await user.click(within(dialog).getByRole("button", { name: "Add the product" }));

    expect(await screen.findByText("Product added")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "ONLINE DRIPPER 8 LPH" })).toBeInTheDocument();
  });

  it("confirms a stand-in MRP and gives a product its first HSN code", async () => {
    const user = show(<ProductMaster />);
    await user.click(
      await screen.findByRole("button", { name: /^EMITTING PIPE 16 MM 40 CM SPACING 2 LPH/ }),
    );
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByText(/No HSN code yet/)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("HSN code"), "3917");
    await user.click(within(dialog).getByRole("button", { name: "Set HSN" }));
    expect(await screen.findByText(/^HSN 3917 from/)).toBeInTheDocument();

    expect(within(dialog).getByText("Nothing changed yet.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(/^MRP/), "42");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Product saved")).toBeInTheDocument();
  });

  it("shows the catalogue read-only to a field employee", async () => {
    signInAs("employee");
    const user = show(<ProductMaster />);
    await screen.findByRole("list", { name: "Products" });

    expect(screen.queryByRole("button", { name: "New product" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^INLINE DRIPPER 4 LPH/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Description")).toBeDisabled();
    expect(within(dialog).queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Change HSN" })).not.toBeInTheDocument();
  });
});

describe("[MSTR-005] ProductMaster tax rates", () => {
  beforeEach(() => {
    signInAs("admin");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
  });

  it("lists the rates in force and sets a slab for a code", async () => {
    const user = show(<ProductMaster />, "?tab=tax-rates");
    const rates = await screen.findByRole("list", { name: "GST rates" });
    expect(within(rates).getAllByRole("listitem")).toHaveLength(4);

    await user.click(screen.getByRole("button", { name: "Set a rate" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Set the rate" }));
    expect(within(dialog).getByText("Four to eight digits.")).toBeInTheDocument();
    expect(within(dialog).getByText("Choose the slab.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("HSN code"), "3917");
    await user.click(within(dialog).getByRole("combobox", { name: "GST slab" }));
    await user.click(await screen.findByRole("option", { name: "18 %" }));
    await user.click(within(dialog).getByRole("button", { name: "Set the rate" }));

    expect(await screen.findByText("HSN 3917: GST 18 %")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        within(screen.getByRole("list", { name: "GST rates" })).getAllByRole("listitem"),
      ).toHaveLength(5);
    });
  });
});

describe("[MSTR-006] Price lists", () => {
  beforeEach(() => {
    signInAs("admin");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
    push.mockReset();
  });

  it("lists drafts and published lists with where each stands", async () => {
    show(<ProductMaster />, "?tab=price-lists");
    const lists = await screen.findByRole("list", { name: "Price lists" });

    expect(
      within(lists).getByRole("link", { name: "Gujarat dealers, November, Draft" }),
    ).toBeInTheDocument();
    expect(within(lists).getByRole("link", { name: "GJ 2026-27, In force" })).toBeInTheDocument();
    expect(within(lists).getByRole("link", { name: "GJ 2025-26, Ended" })).toBeInTheDocument();
  });

  it("starts a draft and opens its rate sheet", async () => {
    const user = show(<ProductMaster />, "?tab=price-lists");
    await user.click(await screen.findByRole("button", { name: "New price list" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Name"), "Gujarat farmers, December");
    await user.click(within(dialog).getByRole("button", { name: "Start the draft" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(expect.stringMatching(/^\/products\/price-lists\//));
    });
  });

  it("keeps a bad rate from being saved, then saves the edits over the list's rates", async () => {
    const listId = listNamed("Gujarat dealers, November");
    const user = show(<PriceListSheet listId={listId} />);
    const rates = await screen.findByRole("list", { name: "Rates" });
    const elbow = within(rates).getByLabelText("PVC ELBOW 90 MM");

    await user.type(elbow, "180.555");
    expect(
      within(rates).getByText("At most two decimals: rates aren't rounded."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save rates" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled();

    await user.clear(elbow);
    await user.type(elbow, "180.50");
    await user.click(screen.getByRole("button", { name: "Save rates" }));

    expect(await screen.findByText("1 rate saved")).toBeInTheDocument();
    const list = mockDb.priceLists.find((item) => item.id === listId);
    expect(list?.rates.size).toBe(3);
  });

  it("publishes a list missing rates only once that is ticked", async () => {
    const user = show(<PriceListSheet listId={listNamed("Gujarat dealers, November")} />);
    await user.click(await screen.findByRole("button", { name: "Publish" }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Publish" });

    expect(confirm).toBeDisabled();
    await user.click(within(dialog).getByRole("checkbox", { name: /Publish without rates for 7/ }));
    await user.click(confirm);

    expect(await screen.findByText("Gujarat dealers, November published")).toBeInTheDocument();
    expect(await screen.findByText("Published, starts later")).toBeInTheDocument();
  });

  it("shows a published list read-only, with no way to change its rates", async () => {
    signInAs("employee");
    show(<PriceListSheet listId={listNamed("GJ 2026-27")} />);
    const rates = await screen.findByRole("list", { name: "Rates" });

    expect(within(rates).queryAllByRole("textbox")).toHaveLength(0);
    expect(screen.getByText(/A published list never changes/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "New list from this one" }),
    ).not.toBeInTheDocument();
  });
});

describe("[MSTR-008] Price lists by sale type", () => {
  beforeEach(() => {
    signInAs("admin");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
    push.mockReset();
  });

  it("starts a list for one sale type, and finds it by that type", async () => {
    let sent: unknown = null;
    server.events.on("request:start", ({ request }) => {
      if (request.method === "POST" && new URL(request.url).pathname.endsWith("/price-lists")) {
        void request
          .clone()
          .json()
          .then((body: unknown) => {
            sent = body;
          });
      }
    });
    const user = show(<ProductMaster />, "?tab=price-lists");
    await user.click(await screen.findByRole("button", { name: "New price list" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Name"), "Subsidy rates Gujarat");
    expect(within(dialog).getByRole("combobox", { name: "Sale type" })).toHaveTextContent(
      "All sale types",
    );
    await user.click(within(dialog).getByRole("combobox", { name: "Sale type" }));
    await user.click(await screen.findByRole("option", { name: "Subsidy" }));
    await user.click(within(dialog).getByRole("button", { name: "Start the draft" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(expect.stringMatching(/^\/products\/price-lists\//));
    });
    expect(sent).toMatchObject({ name: "Subsidy rates Gujarat", sales_type: "subsidised" });
    expect(
      mockDb.priceLists.find((list) => list.name === "Subsidy rates Gujarat")?.sales_type,
    ).toBe("subsidised");
    server.events.removeAllListeners("request:start");
  });

  it("says each list's sale type, and filters by it", async () => {
    const draft = mockDb.priceLists.find((list) => list.status === "draft");
    if (draft !== undefined) draft.sales_type = "industrial";
    const user = show(<ProductMaster />, "?tab=price-lists");
    const lists = await screen.findByRole("list", { name: "Price lists" });
    expect(within(lists).getAllByText("All sale types").length).toBeGreaterThan(0);
    expect(within(lists).getByText("Industrial")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Sale type/ }));
    await user.click(await screen.findByRole("radio", { name: /^Industrial/ }));

    await waitFor(() => {
      expect(
        within(screen.getByRole("list", { name: "Price lists" })).getAllByRole("listitem"),
      ).toHaveLength(1);
    });
  });
});

describe("[MSTR-007] Import rates from Excel", () => {
  beforeEach(() => {
    signInAs("admin");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
    push.mockReset();
  });

  const RATES = ["Item Code,Net Rate", "PL-1001,15.20", "PL-9999,120", "PL-1002,3.95"].join("\n");

  it("uploads a sheet, matches its columns, names the bad rows and imports the good ones", async () => {
    const listId = listNamed("Gujarat dealers, November");
    const user = show(<PriceListSheet listId={listId} />);
    await user.click(await screen.findByRole("button", { name: "Import from Excel" }));
    const dialog = await screen.findByRole("dialog", { name: "Import rates from Excel" });

    expect(within(dialog).getByRole("button", { name: "Upload" })).toBeDisabled();
    await user.upload(
      within(dialog).getByTestId("import-file-input"),
      new File([RATES], "rates.csv", { type: "text/csv" }),
    );
    expect(within(dialog).getByText("rates.csv")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Upload" }));

    // Step 2: the backend's suggestion is filled in, column by column.
    const columns = await within(dialog).findByRole("list", { name: "Columns in your file" });
    expect(within(columns).getByRole("combobox", { name: "Item Code" })).toHaveTextContent(
      "Item code",
    );
    expect(within(columns).getByRole("combobox", { name: "Net Rate" })).toHaveTextContent(
      "Rate (required)",
    );
    expect(within(columns).getByText("PL-1001 · PL-9999")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("radio", { name: /Merge/ }));
    await user.click(within(dialog).getByRole("button", { name: "Check the rows" }));

    // Step 3: counts, the bad row with its reason, and the good rows.
    expect(await within(dialog).findByText("2 ready")).toBeInTheDocument();
    expect(within(dialog).getByText("1 with errors")).toBeInTheDocument();
    const errors = within(dialog).getByRole("table", { name: /Rows with errors/ });
    expect(within(errors).getByText("no product with item code PL-9999")).toBeInTheDocument();
    // The preview names the product the code found, as the backend sends it, and no ids.
    const preview = within(dialog).getByRole("table", { name: /Ready rows/ });
    expect(within(preview).getByRole("columnheader", { name: "Product" })).toBeInTheDocument();
    expect(within(preview).queryByRole("columnheader", { name: /id$/i })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Import 2 rates" })).toBeDisabled();

    await user.click(within(dialog).getByRole("button", { name: "Import good rows only" }));

    expect(await within(dialog).findByText("2 rates written, 1 skipped.")).toBeInTheDocument();
    expect(await screen.findByText("2 rates imported")).toBeInTheDocument();
    const rates = mockDb.priceLists.find((list) => list.id === listId)?.rates;
    expect(rates?.get(mockDb.products.find((item) => item.item_code === "PL-1001")?.id ?? "")).toBe(
      "15.20",
    );
  });

  it("puts a mapping problem on its field, and discards the upload when closed", async () => {
    const user = show(<PriceListSheet listId={listNamed("Gujarat dealers, November")} />);
    await user.click(await screen.findByRole("button", { name: "Import from Excel" }));
    const dialog = await screen.findByRole("dialog", { name: "Import rates from Excel" });
    await user.upload(
      within(dialog).getByTestId("import-file-input"),
      new File([RATES], "rates.csv", { type: "text/csv" }),
    );
    await user.click(within(dialog).getByRole("button", { name: "Upload" }));
    const columns = await within(dialog).findByRole("list", { name: "Columns in your file" });
    await user.click(within(columns).getByRole("combobox", { name: "Net Rate" }));
    await user.click(await screen.findByRole("option", { name: "Skip this column" }));

    expect(within(dialog).getByText("Still to match: Rate.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Check the rows" }));
    // The backend refuses the mapping (`mapping.rate: required`): it stays on matching.
    expect(
      await within(dialog).findByText("Match the columns named below, then check again."),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Still to match: Rate.")).toBeInTheDocument();
    expect(within(dialog).queryByText(/ready$/)).not.toBeInTheDocument();

    const [batch] = [...mockDb.imports.values()];
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(batch?.status).toBe("discarded");
    });
  });

  it("offers no import on a published list", async () => {
    show(<PriceListSheet listId={listNamed("GJ 2026-27")} />);
    await screen.findByRole("list", { name: "Rates" });

    expect(screen.queryByRole("button", { name: "Import from Excel" })).not.toBeInTheDocument();
  });
});
