import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { listPartners } from "@/features/partners/api/partners.api";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { PartnerDetail } from "./partner-detail";
import { EditPartner, NewPartner } from "./partner-pages";
import { PartnersList } from "./partners-list";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), notFound: vi.fn() }));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(ui: React.JSX.Element, searchParams = ""): ReturnType<typeof userEvent.setup> {
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

function idOf(name: string): string {
  const partner = mockDb.partners.find((item) => item.name === name);
  if (partner === undefined) throw new Error(`No ${name}`);
  return partner.id;
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
  push.mockReset();
}

describe("[CHNL-001] PartnersList", () => {
  beforeEach(reset);
  afterEach(reset);

  it("lists the open partners with their type, code, parent, place and users", async () => {
    signInAs("admin");
    show(<PartnersList />);
    const list = await screen.findByRole("list", { name: "Partners" });
    const dealer = within(list).getByRole("link", {
      name: "Khodiyar Irrigation, Dealer, CP-004",
    });
    expect(dealer).toHaveTextContent("CP-004 · under Saurashtra Agro Distributors");
    expect(dealer).toHaveTextContent("Rajkot");
    expect(dealer).toHaveTextContent("1 user");
    // Open partners by default: the closed one waits behind the Status filter.
    expect(within(list).queryByRole("link", { name: /Balagam/ })).not.toBeInTheDocument();
    expect(screen.getByText("11 partners, newest first.")).toBeInTheDocument();
  });

  it("finds the closed ones, and the partners under one, from the URL", async () => {
    signInAs("admin");
    show(<PartnersList />, `?status=closed`);
    const list = await screen.findByRole("list", { name: "Partners" });
    expect(within(list).getAllByRole("link")).toHaveLength(1);
    expect(within(list).getByRole("link", { name: /Balagam Krishi Seva.*closed/ })).toBeVisible();
  });

  it("names the parent filter, and says why nothing matches", async () => {
    signInAs("admin");
    show(<PartnersList />, `?parent=${idOf("Virpur Agro Point")}`);
    expect(await screen.findByText("Under Virpur Agro Point")).toBeInTheDocument();
    expect(await screen.findByText("No partner matches these filters")).toBeInTheDocument();
  });

  it("offers New partner and the Excel import to those who may add partners, not to others", async () => {
    signInAs("admin");
    show(<PartnersList />);
    await screen.findByRole("list", { name: "Partners" });
    expect(screen.getByRole("link", { name: "New partner" })).toHaveAttribute(
      "href",
      "/partners/new",
    );
    expect(screen.getByRole("button", { name: "Import from Excel" })).toBeEnabled();
  });

  it("shows a field officer the list without New partner or the import", async () => {
    signInAs("employee");
    show(<PartnersList />);
    await screen.findByRole("list", { name: "Partners" });
    expect(screen.queryByRole("link", { name: "New partner" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import from Excel" })).not.toBeInTheDocument();
  });
});

describe("[CHNL-002] NewPartner", () => {
  beforeEach(reset);
  afterEach(reset);

  it("names what is missing before sending, and asks a dealer for its distributor", async () => {
    signInAs("admin");
    const user = show(<NewPartner parentId={null} />);
    const form = await screen.findByRole("form", { name: "New partner" });
    await user.click(within(form).getByRole("button", { name: "Dealer" }));
    await user.click(within(form).getByRole("button", { name: "Add the partner" }));

    expect(within(form).getByText("Choose the distributor it sits under.")).toBeInTheDocument();
    expect(within(form).getByText("Enter the partner's code.")).toBeInTheDocument();
    expect(within(form).getByText("Enter the business name.")).toBeInTheDocument();
    expect(within(form).getByText("Choose where it works.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("starts as the next type down under the partner it came from, and adds it", async () => {
    signInAs("admin");
    const parentId = idOf("Sorath Agri Distributors");
    const user = show(<NewPartner parentId={parentId} />);
    const form = await screen.findByRole("form", { name: "New partner" });
    expect(within(form).getByRole("button", { name: "Dealer" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(form).getByRole("combobox", { name: "Under which distributor" })).toHaveValue(
      "Sorath Agri Distributors",
    );
    expect(within(form).getByRole("combobox", { name: "Territory" })).toHaveValue("Junagadh");

    await user.type(within(form).getByRole("textbox", { name: "Code" }), "DL-JND-9");
    await user.type(
      within(form).getByRole("textbox", { name: "Business name" }),
      "Keshod Krishi Kendra",
    );
    await user.type(within(form).getByRole("textbox", { name: "GSTIN (optional)" }), "24abc");
    await user.click(within(form).getByRole("button", { name: "Add the partner" }));
    expect(
      within(form).getByText("A GSTIN is 15 characters, like 24ABCDE1234F1Z5."),
    ).toBeInTheDocument();

    await user.clear(within(form).getByRole("textbox", { name: "GSTIN (optional)" }));
    await user.click(within(form).getByRole("button", { name: "Add the partner" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(`/partners/${idOf("Keshod Krishi Kendra")}`);
    });
    expect(await screen.findByText("Keshod Krishi Kendra added")).toBeInTheDocument();
    const made = mockDb.partners.find((item) => item.name === "Keshod Krishi Kendra");
    expect(made).toMatchObject({ partner_type: "dealer", parent_id: parentId, code: "DL-JND-9" });
  });

  it("puts a used code back on its field", async () => {
    signInAs("admin");
    const user = show(<NewPartner parentId={idOf("Sorath Agri Distributors")} />);
    const form = await screen.findByRole("form", { name: "New partner" });
    await user.type(within(form).getByRole("textbox", { name: "Code" }), "CP-003");
    await user.type(within(form).getByRole("textbox", { name: "Business name" }), "Any Agro");
    await user.click(within(form).getByRole("button", { name: "Add the partner" }));

    expect(await within(form).findByText("Already in use.")).toBeInTheDocument();
    expect(within(form).getByRole("textbox", { name: "Code" })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("tells someone without partners.create they can't add partners", async () => {
    signInAs("employee");
    show(<NewPartner parentId={null} />);
    expect(await screen.findByText("You can't add partners")).toBeInTheDocument();
  });
});

describe("[CHNL-002] On the portal: a dealer adds its own sub-dealers", () => {
  beforeEach(reset);
  afterEach(reset);

  it("lists the dealer's own business and what is under it, with Add a sub-dealer", async () => {
    signInAs("dealer");
    show(<PartnersList />);
    const list = await screen.findByRole("list", { name: "Partners" });
    expect(within(list).getByRole("link", { name: /Shah Agro Traders/ })).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: /Kisan Seva Kendra/ })).toBeInTheDocument();
    expect(within(list).queryByRole("link", { name: /Saurashtra Agro/ })).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Add a sub-dealer" })).toHaveAttribute(
      "href",
      "/partners/new",
    );
    expect(screen.queryByRole("link", { name: "New partner" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import from Excel" })).not.toBeInTheDocument();
  });

  it("adds a sub-dealer under the dealer itself, with the type and the dealer fixed", async () => {
    signInAs("dealer");
    const mine = mockMeFor("dealer").data.partner?.id ?? "";
    // Whatever the address says, a dealer adds under itself.
    const user = show(<NewPartner parentId={idOf("Sorath Agri Distributors")} />);
    const form = await screen.findByRole("form", { name: "New partner" });
    expect(within(form).getByRole("textbox", { name: "Type" })).toHaveValue("Sub-dealer");
    expect(within(form).getByRole("textbox", { name: "Under which dealer" })).toHaveValue(
      "Shah Agro Traders",
    );
    expect(within(form).queryByRole("button", { name: "Distributor" })).not.toBeInTheDocument();
    expect(within(form).queryByLabelText(/Credit limit/)).not.toBeInTheDocument();

    await user.type(within(form).getByRole("textbox", { name: "Code" }), "SD-RJK-1");
    await user.type(within(form).getByRole("textbox", { name: "Business name" }), "Gondal Agro");
    await user.click(within(form).getByRole("button", { name: "Add the partner" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(`/partners/${idOf("Gondal Agro")}`);
    });
    expect(mockDb.partners.find((item) => item.name === "Gondal Agro")).toMatchObject({
      partner_type: "sub_dealer",
      parent_id: mine,
      credit_limit: null,
    });
  });

  it("offers a distributor Add a dealer, and a sub-dealer no Channel partners at all", async () => {
    signInAs("distributor");
    show(<PartnersList />);
    expect(await screen.findByRole("link", { name: "Add a dealer" })).toBeInTheDocument();

    signInAs("sub_dealer");
    expect(
      await listPartners({
        cursor: null,
        q: "",
        type: null,
        active: true,
        parentId: null,
      }).then(
        () => "listed",
        (error: unknown) => (isApiError(error) ? error.status : null),
      ),
    ).toBe(403);
  });

  it("offers Add a sub-dealer on the dealer's own page only", async () => {
    signInAs("dealer");
    const view = renderWithProviders(<PartnerDetail partnerId={idOf("Shah Agro Traders")} />);
    expect(await screen.findByRole("link", { name: "Add a sub-dealer" })).toBeInTheDocument();
    view.unmount();

    renderWithProviders(<PartnerDetail partnerId={idOf("Kisan Seva Kendra")} />);
    await screen.findByRole("heading", { name: "Kisan Seva Kendra" });
    expect(screen.queryByRole("link", { name: /^Add a/ })).not.toBeInTheDocument();
  });
});

describe("[CHNL-003] EditPartner", () => {
  beforeEach(reset);
  afterEach(reset);

  it("sends only what changed, and keeps the code and type fixed", async () => {
    signInAs("admin");
    const id = idOf("Patel Agro Traders");
    const user = show(<EditPartner partnerId={id} />);
    const form = await screen.findByRole("form", { name: "Edit Patel Agro Traders" });
    expect(within(form).getByRole("textbox", { name: "Code" })).toBeDisabled();
    expect(within(form).queryByRole("button", { name: "Dealer" })).not.toBeInTheDocument();
    expect(within(form).getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(within(form).getByText("Nothing changed yet.")).toBeInTheDocument();

    // Credit terms are staff's: they show once the session is read.
    const terms = await within(form).findByRole("textbox", {
      name: "Payment terms in days (optional)",
    });
    await user.clear(terms);
    await user.type(terms, "400");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    expect(within(form).getByText("Whole days, 0 to 365.")).toBeInTheDocument();

    await user.clear(terms);
    await user.type(terms, "21");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(`/partners/${id}`);
    });
    expect(mockDb.partners.find((item) => item.id === id)?.payment_terms_days).toBe(21);
  });
});

describe("[CHNL-004] PartnerDetail", () => {
  beforeEach(reset);
  afterEach(reset);

  it("shows where it sits, its business, contact and credit terms", async () => {
    signInAs("admin");
    show(<PartnerDetail partnerId={idOf("Saurashtra Agro Distributors")} />);
    const page = await screen.findByRole("article", { name: "Saurashtra Agro Distributors" });
    expect(within(page).getByText("CP-001 · Distributor")).toBeInTheDocument();
    expect(within(page).getByText("Nobody: a distributor sits at the top")).toBeInTheDocument();
    expect(within(page).getByRole("link", { name: "See the dealers under it" })).toHaveAttribute(
      "href",
      `/partners?parent=${idOf("Saurashtra Agro Distributors")}&status=all`,
    );
    expect(await within(page).findByRole("link", { name: "Add a dealer" })).toBeInTheDocument();
    expect(await within(page).findByText("₹5,00,000")).toBeInTheDocument();
    expect(within(page).getByText("45 days")).toBeInTheDocument();
  });

  it("closes a partner after saying its users will be signed out, then reopens it", async () => {
    signInAs("admin");
    const id = idOf("Khodiyar Irrigation");
    const user = show(<PartnerDetail partnerId={id} />);
    await user.click(await screen.findByRole("button", { name: "Close" }));
    const dialog = await screen.findByRole("dialog", { name: "Close Khodiyar Irrigation?" });
    expect(dialog).toHaveTextContent("Its 1 user is signed out everywhere and deactivated.");
    await user.click(within(dialog).getByRole("button", { name: "Close the partner" }));

    expect(await screen.findByText("Khodiyar Irrigation is closed")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Reopen" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reopen" }));
    const again = await screen.findByRole("dialog", { name: "Reopen Khodiyar Irrigation?" });
    await user.click(within(again).getByRole("button", { name: "Reopen" }));
    expect(
      await screen.findByText(
        "Khodiyar Irrigation is open again. Its 1 user stays deactivated until reactivated in Users & roles.",
      ),
    ).toBeInTheDocument();
  });

  it("shows a field officer the partner without credit terms or actions", async () => {
    signInAs("employee");
    const asked: string[] = [];
    server.events.on("request:start", ({ request }) => {
      asked.push(new URL(request.url).pathname);
    });
    show(<PartnerDetail partnerId={idOf("Saurashtra Agro Distributors")} />);
    const page = await screen.findByRole("article", { name: "Saurashtra Agro Distributors" });
    expect(within(page).queryByText("Credit terms")).not.toBeInTheDocument();
    expect(within(page).queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
    // APP-009 (live test X-03) · nothing asked that the backend refuses a field officer.
    expect(asked.filter((path) => /\/(ledger|credit|dealer-rating)$/.test(path))).toEqual([]);
    server.events.removeAllListeners();
  });

  it("asks a partner editor for the credit, but not for the ledger or rating (APP-009, X-03)", async () => {
    signInAs("state_manager");
    const asked: string[] = [];
    server.events.on("request:start", ({ request }) => {
      asked.push(new URL(request.url).pathname);
    });
    show(<PartnerDetail partnerId={idOf("Saurashtra Agro Distributors")} />);
    await screen.findByRole("article", { name: "Saurashtra Agro Distributors" });
    await waitFor(() => {
      expect(asked.some((path) => path.endsWith("/credit"))).toBe(true);
    });
    expect(asked.filter((path) => /\/(ledger|dealer-rating)$/.test(path))).toEqual([]);
    server.events.removeAllListeners();
  });
});

describe("[CHNL-006] GSTIN details on the partner form", () => {
  beforeEach(reset);
  afterEach(reset);

  it("shows the GST record for a GSTIN it finds, and fills the names, PAN and address on request", async () => {
    signInAs("admin");
    const user = show(<NewPartner parentId={null} />);
    const form = await screen.findByRole("form", { name: "New partner" });
    await user.type(
      within(form).getByRole("textbox", { name: "GSTIN (optional)" }),
      "24aaacp1234f1z5",
    );

    expect(
      await within(form).findByText("Patel Agro Irrigation Private Limited"),
    ).toBeInTheDocument();
    expect(within(form).getByText("Active")).toBeInTheDocument();
    expect(within(form).getByRole("textbox", { name: "Business name" })).toHaveValue("");

    await user.click(within(form).getByRole("button", { name: "Use these details" }));

    expect(within(form).getByRole("textbox", { name: "Business name" })).toHaveValue("Patel Agro");
    expect(within(form).getByRole("textbox", { name: "PAN (optional)" })).toHaveValue("AAACP1234F");
    expect(within(form).getByRole("textbox", { name: "Address (optional)" })).toHaveValue(
      "Plot 14, GIDC Estate, Anand, Gujarat 388001",
    );
    // Still the officer's to change.
    await user.clear(within(form).getByRole("textbox", { name: "Business name" }));
    await user.type(
      within(form).getByRole("textbox", { name: "Business name" }),
      "Patel Agro Anand",
    );
    expect(within(form).getByRole("textbox", { name: "Business name" })).toHaveValue(
      "Patel Agro Anand",
    );
  });

  it("asks for the names by hand while GST details can't be fetched, or no record is found", async () => {
    signInAs("admin");
    const user = show(<NewPartner parentId={null} />);
    const form = await screen.findByRole("form", { name: "New partner" });
    const gstin = within(form).getByRole("textbox", { name: "GSTIN (optional)" });
    await user.type(gstin, "24ABCDE1234F1Z5");
    expect(
      await within(form).findByText("GST details can't be fetched yet. Type the names yourself."),
    ).toBeInTheDocument();

    server.use(
      http.get(buildApiUrl("/gstin/:gstin"), ({ params }) =>
        HttpResponse.json({
          data: {
            gstin: String(params.gstin),
            valid: true,
            reason: null,
            state_code: "24",
            pan: "ABCDE5678F",
            lookup: "not_found",
          },
        }),
      ),
    );
    await user.clear(gstin);
    await user.type(gstin, "24ABCDE5678F1Z5");
    expect(
      await within(form).findByText("No GST record found for this GSTIN. Type the names yourself."),
    ).toBeInTheDocument();
    expect(
      within(form).queryByRole("button", { name: "Use these details" }),
    ).not.toBeInTheDocument();
  });

  it("doesn't look a GSTIN up until it is complete", async () => {
    signInAs("admin");
    let lookups = 0;
    server.use(
      http.get(buildApiUrl("/gstin/:gstin"), () => {
        lookups += 1;
        return HttpResponse.json({ error: { code: "internal", message: "Down" } }, { status: 500 });
      }),
    );
    const user = show(<NewPartner parentId={null} />);
    const form = await screen.findByRole("form", { name: "New partner" });
    await user.type(
      within(form).getByRole("textbox", { name: "GSTIN (optional)" }),
      "24AAACP1234F1Z",
    );
    expect(lookups).toBe(0);

    await user.type(within(form).getByRole("textbox", { name: "GSTIN (optional)" }), "5");
    expect(
      await within(form).findByText("Couldn't check the GST record. Type the names yourself."),
    ).toBeInTheDocument();
    expect(lookups).toBe(1);
  });
});
