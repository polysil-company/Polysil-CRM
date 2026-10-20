import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommandMenu } from "@/components/layout/command-menu";
import { listAssistantActions, searchAssistant } from "@/features/assistant/api/assistant.api";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { HelpPage } from "./help-page";

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push: router.push, replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/dashboard",
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
  router.push.mockReset();
}

async function statusOf(call: Promise<unknown>): Promise<number | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? (error.status ?? null) : null;
}

/** A lead handed to the dealer for this test, and one it doesn't hold. */
function leads(): { dealers: string; others: string } {
  const partner = mockMeFor("dealer").data.partner;
  const [held, other] = mockDb.leads.filter((lead) => lead.stage !== "merged");
  if (partner === null || partner === undefined || held === undefined || other === undefined) {
    throw new Error("Mock data changed.");
  }
  held.assigned_partner = {
    id: partner.id,
    name: partner.name ?? "Dealer",
    partner_type: "dealer",
  };
  if (other.assigned_partner?.id === partner.id) other.assigned_partner = null;
  return { dealers: held.inquiry_no, others: other.inquiry_no };
}

describe("[BOT-001] Assistant search (contract)", () => {
  afterEach(reset);

  it("gives a starter set for nothing typed, and records only from 3 characters", async () => {
    reset();
    const starter = await searchAssistant("");
    expect(starter.actions.map((action) => action.key)).toEqual(
      expect.arrayContaining(["lead.create", "quotation.create"]),
    );
    expect(starter.records).toEqual([]);

    const number = leads().others;
    expect((await searchAssistant(number.slice(-2))).records).toEqual([]);
    const found = await searchAssistant(number);
    expect(found.records[0]).toMatchObject({ kind: "lead", screen: "leads.detail" });
    expect(found.records[0]?.label).toContain(number);
  });

  it("matches actions by words in any order, best first", async () => {
    reset();
    const answer = await searchAssistant("quotation new");
    expect(answer.actions[0]?.key).toBe("quotation.create");
    expect(answer.records).toEqual([]);
  });

  it("finds a quotation by its serial alone", async () => {
    reset();
    const quotation = mockDb.quotations.find((row) => row.quote_no !== null);
    const serial = quotation?.quote_no?.split("/").at(-1);
    if (quotation === undefined || serial === undefined) throw new Error("Mock data changed.");
    const answer = await searchAssistant(String(Number(serial)).padStart(3, "0"));
    expect(answer.records.map((record) => record.id)).toContain(quotation.id);
  });

  it("scopes a dealer's records and actions", async () => {
    reset();
    const { dealers, others } = leads();
    writeMockRole("dealer");
    expect((await searchAssistant(dealers)).records[0]?.label).toContain(dealers);
    expect((await searchAssistant(others)).records).toEqual([]);
    const keys = (await listAssistantActions()).map((action) => action.key);
    expect(keys).not.toContain("message.list");
    expect(keys).not.toContain("user.create");
  });

  it("refuses a long query or a limit out of range with 422", async () => {
    reset();
    expect(await statusOf(searchAssistant("x".repeat(101)))).toBe(422);
    const response = await fetch(buildApiUrl("/assistant?q=&limit=0"));
    expect(response.status).toBe(422);
  });

  it("leaves out a screen or a kind this app doesn't know yet", async () => {
    reset();
    server.use(
      http.get(buildApiUrl("/assistant"), () =>
        HttpResponse.json({
          data: {
            actions: [
              { key: "a", title: "Known", hint: "", screen: "leads.list", module: "leads" },
              { key: "b", title: "Later", hint: "", screen: "fleet.new", module: "fleet" },
            ],
            records: [
              { kind: "invoice", id: "1", label: "INV/1", screen: "orders.detail" },
              { kind: "lead", id: "2", label: "POL/1", screen: "leads.detail" },
            ],
          },
        }),
      ),
    );
    const answer = await searchAssistant("abc");
    expect(answer.actions.map((action) => action.key)).toEqual(["a"]);
    expect(answer.records.map((record) => record.id)).toEqual(["2"]);
  });
});

describe("[BOT-001] CommandMenu", () => {
  afterEach(reset);

  it("starts an action the server matched", async () => {
    reset();
    signInAs("admin");
    const user = userEvent.setup();
    renderWithProviders(<CommandMenu open onOpenChange={vi.fn()} />);
    await user.type(await screen.findByRole("combobox"), "new quotation");
    const actions = await screen.findByRole("group", { name: "Actions" });
    await user.click(await within(actions).findByText("New quotation"));
    expect(router.push).toHaveBeenCalledWith("/quotations/new");
  });

  it("opens a lead found by its number", async () => {
    reset();
    signInAs("admin");
    const number = leads().others;
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    renderWithProviders(<CommandMenu open onOpenChange={onOpenChange} />);
    await user.type(await screen.findByRole("combobox"), number);
    const records = await screen.findByRole("group", { name: "Records" }, { timeout: 3000 });
    await user.click(within(records).getByText(new RegExp(number.replaceAll("/", "\\/"))));
    const lead = mockDb.leads.find((row) => row.inquiry_no === number);
    expect(router.push).toHaveBeenCalledWith(`/leads/${lead?.id ?? ""}`);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("keeps pages working when the search fails", async () => {
    reset();
    signInAs("admin");
    server.use(
      http.get(buildApiUrl("/assistant"), () =>
        HttpResponse.json({ error: { code: "server_error", message: "Down" } }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<CommandMenu open onOpenChange={vi.fn()} />);
    await user.type(await screen.findByRole("combobox"), "leads");
    expect(await screen.findByText(/Couldn.t search records just now/)).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "Leads" })).toBeInTheDocument();
  });
});

describe("[BOT-002] Help page", () => {
  afterEach(reset);

  it("lists what the user may do by module, and filters it", async () => {
    reset();
    const user = userEvent.setup();
    renderWithProviders(<HelpPage />);
    expect(await screen.findByRole("heading", { name: "Quotations" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /New quotation/ })).toHaveAttribute(
      "href",
      "/quotations/new",
    );
    await user.type(screen.getByRole("searchbox", { name: "Filter what you can do" }), "payment");
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Quotations" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: /Record a payment/ })).toBeInTheDocument();
  });

  it("shows a dealer only their own actions", async () => {
    reset();
    writeMockRole("dealer");
    renderWithProviders(<HelpPage />);
    await screen.findAllByRole("link");
    expect(screen.queryByRole("link", { name: /Add a user/ })).not.toBeInTheDocument();
  });
});
