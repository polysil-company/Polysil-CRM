import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
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
    expect(screen.getByText("8 partners, newest first.")).toBeInTheDocument();
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
    show(<PartnerDetail partnerId={idOf("Saurashtra Agro Distributors")} />);
    const page = await screen.findByRole("article", { name: "Saurashtra Agro Distributors" });
    expect(within(page).queryByText("Credit terms")).not.toBeInTheDocument();
    expect(within(page).queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  });
});
