import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  getCustomer,
  getCustomerTimeline,
  listCustomers,
  patchCustomer,
} from "@/features/customers/api/customers.api";
import type { CustomerWire } from "@/features/customers/api/customers.schemas";
import { getLead } from "@/features/leads/api/leads.api";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { CustomerDetail } from "./customer-detail";
import { draftOf, draftProblems, patchOf } from "./customer-edit-dialog";
import { CustomersSearch } from "./customers-search";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

let keys = 0;
function key(): string {
  keys += 1;
  return `customer-${String(keys)}`;
}

async function codeOf(call: Promise<unknown>): Promise<string | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? (error.code ?? null) : null;
}

function seeded(withConsent: boolean): CustomerWire {
  const customer = mockDb.customers.find(
    (item) => (item.consent_given_at !== null) === withConsent,
  );
  if (customer === undefined) throw new Error("No seeded customer");
  return customer;
}

describe("[LEAD-016] Customers search (contract)", () => {
  afterEach(reset);

  it("lists the customers newest first, and ignores a search under three characters", async () => {
    reset();
    const all = await listCustomers({ q: "", territoryId: null, cursor: null });
    expect(all.items.length).toBeGreaterThan(0);
    const dates = all.items.map((customer) => customer.createdAt);
    expect(dates).toEqual([...dates].sort((left, right) => right.localeCompare(left)));
    const short = await listCustomers({ q: "ab", territoryId: null, cursor: null });
    expect(short.items.map((customer) => customer.id)).toEqual(
      all.items.map((customer) => customer.id),
    );
  });

  it("finds a customer by part of the name, the last digits of the mobile, or the area", async () => {
    reset();
    const customer = seeded(false);
    const byName = await listCustomers({
      q: customer.name.slice(0, 4),
      territoryId: null,
      cursor: null,
    });
    expect(byName.items.some((item) => item.id === customer.id)).toBe(true);
    const byMobile = await listCustomers({
      q: customer.mobile.slice(-5),
      territoryId: null,
      cursor: null,
    });
    expect(byMobile.items.map((item) => item.id)).toContain(customer.id);
    const territoryId = customer.territory?.id ?? null;
    expect(territoryId).not.toBeNull();
    const byArea = await listCustomers({ q: "", territoryId, cursor: null });
    expect(byArea.items.map((item) => item.id)).toContain(customer.id);
    const nobody = await listCustomers({ q: "zzzzqq", territoryId: null, cursor: null });
    expect(nobody.items).toHaveLength(0);
  });
});

describe("[LEAD-017] Customer record (contract)", () => {
  afterEach(reset);

  it("gives the customer's leads, documents and a timeline naming each lead", async () => {
    reset();
    const customer = seeded(false);
    const detail = await getCustomer(customer.id);
    expect(detail.leads.length).toBe(detail.leadCount);
    expect(detail.leads.length).toBeGreaterThan(0);
    const timeline = await getCustomerTimeline({ customerId: customer.id, before: null });
    const onLead = timeline.items.find((event) => event.leadId !== null);
    expect(onLead?.leadCode).toBe(
      detail.leads.find((lead) => lead.id === onLead?.leadId)?.code ?? "missing",
    );
    expect(timeline.items.some((event) => event.kind === "customer.created")).toBe(true);
  });

  it("answers 404 for a customer the user can't see, and links each qualified lead", async () => {
    reset();
    expect(await codeOf(getCustomer("00000000-0000-4000-8000-000000000000"))).toBe("not_found");
    const customer = seeded(false);
    const leadId = mockDb.leads.find((lead) => lead.customer_id === customer.id)?.id ?? "";
    expect((await getLead(leadId)).customerId).toBe(customer.id);
    const open = mockDb.leads.find((lead) => lead.stage === "new")?.id ?? "";
    expect((await getLead(open)).customerId).toBeNull();
  });
});

describe("[LEAD-018] Editing a customer and consent (contract)", () => {
  afterEach(reset);

  it("refuses a dealer, wants the channel with consent, then records and withdraws it", async () => {
    reset();
    const customer = seeded(false);
    writeMockRole("dealer");
    expect(
      await codeOf(
        patchCustomer({ customerId: customer.id, body: { village: "X" }, idempotencyKey: key() }),
      ),
    ).not.toBeNull();
    writeMockRole("admin");
    const missing = await patchCustomer({
      customerId: customer.id,
      body: { consent_given: true },
      idempotencyKey: key(),
    }).catch((caught: unknown) => caught);
    expect(readFieldErrors(missing)).toMatchObject({ consent_channel: expect.any(String) });

    const given = await patchCustomer({
      customerId: customer.id,
      body: { consent_given: true, consent_channel: "verbal" },
      idempotencyKey: key(),
    });
    expect(given.consentGivenAt).not.toBeNull();
    expect(given.consentChannel).toBe("verbal");
    const withdrawn = await patchCustomer({
      customerId: customer.id,
      body: { consent_given: false },
      idempotencyKey: key(),
    });
    expect(withdrawn).toMatchObject({ consentGivenAt: null, consentChannel: null });
    const timeline = await getCustomerTimeline({ customerId: customer.id, before: null });
    expect(timeline.items.filter((event) => event.kind === "customer.updated")).toHaveLength(2);
  });

  it("sends only what changed, and checks the name and email", async () => {
    reset();
    const detail = await getCustomer(seeded(false).id);
    const draft = draftOf(detail);
    expect(patchOf(detail, draft)).toEqual({});
    expect(patchOf(detail, { ...draft, village: "  Navapura " })).toEqual({ village: "Navapura" });
    expect(patchOf(detail, { ...draft, type: "institution" })).toEqual({
      customer_type: "institution",
    });
    expect(draftProblems({ ...draft, name: " " })).toHaveProperty("name");
    expect(draftProblems({ ...draft, email: "not-an-email" })).toHaveProperty("email");
    expect(draftProblems({ ...draft, email: "" })).toEqual({});
  });
});

describe("[LEAD-016] CustomersSearch", () => {
  afterEach(reset);

  it("lists customers, asks for three characters, and narrows by name", async () => {
    reset();
    signInAs("admin");
    const customer = seeded(false);
    const user = userEvent.setup();
    renderWithProviders(<CustomersSearch />);
    const list = await screen.findByRole("list", { name: "Customers" });
    expect(within(list).getAllByRole("link").length).toBeGreaterThan(1);

    const search = screen.getByRole("searchbox", { name: "Find a customer" });
    await user.type(search, "ab");
    expect(await screen.findByText(/Type at least 3 letters or digits/)).toBeInTheDocument();
    await user.clear(search);
    await user.type(search, "zzzzqq");
    expect(await screen.findByText("No customer matches")).toBeInTheDocument();
    await user.clear(search);
    await user.type(search, customer.mobile.slice(-6));
    const link = await screen.findByRole("link", { name: new RegExp(customer.name) });
    expect(link).toHaveAttribute("href", `/customers/${customer.id}`);
  });
});

describe("[LEAD-017] CustomerDetail", () => {
  afterEach(reset);

  it("shows the details, the leads and the timeline, and records consent", async () => {
    reset();
    signInAs("admin");
    const customer = seeded(false);
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <CustomerDetail customerId={customer.id} />
        <Toaster />
      </>,
    );
    expect(await screen.findByRole("heading", { name: customer.name })).toBeInTheDocument();
    expect(screen.getByText("No consent")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Leads" })).getAllByRole("link").length).toBe(
      mockDb.leads.filter((lead) => lead.customer_id === customer.id).length,
    );
    expect(
      await screen.findByRole("list", { name: "Customer timeline, newest first" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Became a customer")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Record consent" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: "Spoken" }));
    await user.click(within(dialog).getByRole("button", { name: "Record consent" }));
    expect(await screen.findByText("Consent recorded")).toBeInTheDocument();
    expect(await screen.findByText("Consent given")).toBeInTheDocument();
    expect(await screen.findByText("recorded the customer's consent")).toBeInTheDocument();
  });

  it("corrects the village through Edit", async () => {
    reset();
    signInAs("admin");
    const customer = seeded(false);
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <CustomerDetail customerId={customer.id} />
        <Toaster />
      </>,
    );
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const form = await screen.findByRole("form", { name: `Edit ${customer.name}` });
    const village = within(form).getByLabelText(/Village/);
    await user.clear(village);
    await user.type(village, "Navapura");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Customer saved")).toBeInTheDocument();
    await waitFor(() => {
      expect(mockDb.customers.find((item) => item.id === customer.id)?.village).toBe("Navapura");
    });
  });

  it("shows a dealer the customer of their lead, without Edit or consent", async () => {
    reset();
    const customer = seeded(false);
    const lead = mockDb.leads.find((item) => item.customer_id === customer.id);
    const partner = mockMeFor("dealer").data.partner;
    if (lead === undefined || partner == null) throw new Error("No lead or dealer");
    lead.assigned_partner = { id: partner.id, name: partner.name ?? "", partner_type: "dealer" };
    signInAs("dealer");
    renderWithProviders(<CustomerDetail customerId={customer.id} />);
    expect(await screen.findByRole("heading", { name: customer.name })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /consent/ })).not.toBeInTheDocument();
  });
});
