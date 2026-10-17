import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  createScheme,
  getStanding,
  listEntitlements,
  listSchemes,
  patchScheme,
} from "@/features/schemes/api/schemes.api";
import type { SchemeCreateRequest } from "@/features/schemes/api/schemes.schemas";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";
import { mockSchemeId } from "@/mocks/data/schemes";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { CreditsList } from "./credits-list";
import { SchemeDetail } from "./scheme-detail";
import { SchemeForm } from "./scheme-form";
import { SchemesList } from "./schemes-list";

const push = vi.fn<(href: string) => void>();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/schemes",
  notFound: () => {
    throw new Error("not found");
  },
}));

const TODAY = todayInIndia();
const LIST = { status: null, type: null, q: "", cursor: null } as const;

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

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
  push.mockReset();
}

function body(overrides: Partial<SchemeCreateRequest> = {}): SchemeCreateRequest {
  return {
    code: "TEST-1",
    name: "A test scheme",
    description: null,
    scheme_type: "order_discount",
    condition: { metric: "order_value", min: "100000", max: null },
    benefit: { kind: "pct", value: "4", cap: null, entitlement_days: null },
    period: null,
    valid_from: TODAY,
    valid_to: null,
    priority: 100,
    stackable: false,
    targets: [],
    ...overrides,
  };
}

describe("[SCHM-001] Schemes, through the API", () => {
  afterEach(reset);

  it("lists every scheme for staff, and only the running ones aimed at a dealer", async () => {
    signInAs("admin");
    const all = await listSchemes(LIST);
    expect(all.items).toHaveLength(6);
    const current = await listSchemes({ ...LIST, status: "current" });
    expect(current.items.every((scheme) => scheme.isCurrent)).toBe(true);

    signInAs("dealer");
    const mine = await listSchemes({ ...LIST, status: "current" });
    expect(mine.items.map((scheme) => scheme.code).sort()).toEqual(
      ["FESTIVE-TARGET", "GJ-DRIP-5", "MONSOON-PTS", "NEXT-3K"].sort(),
    );
    expect(mine.items.flatMap((scheme) => scheme.targets).some((t) => t.type === "partner")).toBe(
      false,
    );
  });
});

describe("[SCHM-002] Creating and changing a scheme, through the API", () => {
  afterEach(reset);

  it("creates one, and refuses a taken code and a period with no end", async () => {
    signInAs("admin");
    const created = await createScheme({ body: body(), idempotencyKey: "k1" });
    expect(created).toMatchObject({ code: "TEST-1", used: false, isCurrent: true });

    await expect(createScheme({ body: body(), idempotencyKey: "k2" })).rejects.toMatchObject({
      status: 409,
      code: "code_taken",
    });
    await expect(
      createScheme({
        body: body({
          code: "TEST-2",
          scheme_type: "period",
          benefit: { kind: "points", value: "100", cap: null, entitlement_days: null },
        }),
        idempotencyKey: "k3",
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: { fields: { period: expect.any(String), valid_to: expect.any(String) } },
    });

    signInAs("state_manager");
    await expect(
      createScheme({ body: body({ code: "TEST-3" }), idempotencyKey: "k4" }),
    ).rejects.toMatchObject({
      status: 403,
    });
  });

  it("keeps a used scheme's terms: only its end date and the switch change", async () => {
    signInAs("admin");
    const used = mockSchemeId(1);
    await expect(
      patchScheme({ schemeId: used, body: { name: "Renamed" }, idempotencyKey: "k1" }),
    ).rejects.toMatchObject({ status: 409, code: "scheme_in_use" });

    const sooner = shiftCalendarDay(TODAY, 20);
    const ended = await patchScheme({
      schemeId: used,
      body: { valid_to: sooner },
      idempotencyKey: "k2",
    });
    expect(ended.validTo).toBe(sooner);
    const off = await patchScheme({
      schemeId: used,
      body: { is_active: false },
      idempotencyKey: "k3",
    });
    expect(off).toMatchObject({ isActive: false, isCurrent: false, name: ended.name });
  });
});

describe("[SCHM-003] Standing, and [SCHM-004] credits, through the API", () => {
  afterEach(reset);

  it("gives a dealer its standing in a period scheme, and refuses any other", async () => {
    signInAs("dealer");
    const standing = await getStanding(mockSchemeId(4), null);
    expect(standing).toMatchObject({ metric: "order_value", min: "500000.000" });
    expect(standing.periodStart).toBe(`${TODAY.slice(0, 7)}-01`);
    await expect(getStanding(mockSchemeId(1), null)).rejects.toMatchObject({
      status: 422,
      code: "not_a_period_scheme",
    });

    signInAs("admin");
    await expect(getStanding(mockSchemeId(4), null)).rejects.toMatchObject({ status: 422 });
  });

  it("lists a dealer's own credits", async () => {
    signInAs("dealer");
    const available = await listEntitlements({
      status: "available",
      partnerId: null,
      cursor: null,
    });
    expect(available.items).toHaveLength(2);
    expect(available.items.every((credit) => credit.partner.id === "prt-201")).toBe(true);

    signInAs("admin");
    const all = await listEntitlements({ status: null, partnerId: null, cursor: null });
    expect(all.items).toHaveLength(4);
  });
});

describe("[SCHM-001] SchemesList", () => {
  afterEach(reset);

  it("shows staff every scheme with its terms, and New scheme to an administrator", async () => {
    signInAs("admin");
    show(<SchemesList />);
    expect(
      await screen.findByRole("link", { name: "Gujarat drip 5% above 2 lakh" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/5% off, up to ₹50,000 · Orders of ₹2,00,000 or more/),
    ).toBeInTheDocument();
    expect(screen.getByText("Scheduled")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New scheme" })).toHaveAttribute(
      "href",
      "/schemes/new",
    );
    expect(screen.getByRole("button", { name: /Status/ })).toBeInTheDocument();
  });

  it("shows a dealer the running schemes aimed at it, with nothing to create", async () => {
    signInAs("dealer");
    show(<SchemesList />);
    expect(await screen.findByRole("link", { name: "Monsoon points" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "3% credit on laterals" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "New scheme" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Status/ })).not.toBeInTheDocument();
  });
});

describe("[SCHM-002] SchemeForm", () => {
  afterEach(reset);

  it("names what's missing, offers only the benefits a type takes, and creates the scheme", async () => {
    signInAs("admin");
    const user = show(<SchemeForm scheme={null} />);

    await user.click(screen.getByRole("button", { name: "Create scheme" }));
    expect(await screen.findByText("Give the scheme a name.")).toBeInTheDocument();
    expect(screen.getByText("2 to 40 letters, digits, - or _.")).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /Points on an order/ }));
    const kinds = screen.getByRole("radiogroup", { name: "Kind of benefit" });
    expect(within(kinds).getAllByRole("radio")).toHaveLength(1);
    expect(screen.queryByLabelText("Benefit cap (₹, optional)")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("Code"), "PTS-NEW");
    await user.type(screen.getByLabelText("Name"), "New points");
    await user.type(screen.getByLabelText("How many points"), "150");
    await user.click(screen.getByRole("button", { name: "Create scheme" }));

    expect(await screen.findByText("Scheme created")).toBeInTheDocument();
    const created = mockDb.schemes.find((scheme) => scheme.code === "PTS-NEW");
    expect(created).toMatchObject({ scheme_type: "order_points", benefit: { kind: "points" } });
    expect(push).toHaveBeenCalledWith(`/schemes/${created?.id ?? ""}`);
  });

  it("lets only the end date change on a scheme that has given benefits", async () => {
    signInAs("admin");
    const used = mockDb.schemes.find((scheme) => scheme.used && scheme.valid_to !== null);
    if (used === undefined) throw new Error("no used scheme with an end date");
    const saved = await listSchemes(LIST);
    const scheme = saved.items.find((item) => item.id === used.id);
    if (scheme === undefined) throw new Error("not listed");
    const user = show(<SchemeForm scheme={scheme} />);

    expect(screen.getByText(/only its end date can change here/)).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toBeDisabled();
    const end = screen.getByLabelText(/Last day/);
    await user.clear(end);
    await user.type(end, shiftCalendarDay(TODAY, 5));
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Scheme saved")).toBeInTheDocument();
    expect(mockDb.schemes.find((item) => item.id === used.id)?.valid_to).toBe(
      shiftCalendarDay(TODAY, 5),
    );
  });
});

describe("[SCHM-001] SchemeDetail", () => {
  afterEach(reset);

  it("shows the terms, names who it's for, and switches the scheme off", async () => {
    signInAs("admin");
    const user = show(<SchemeDetail schemeId={mockSchemeId(1)} />);

    expect(await screen.findByText("5% off, up to ₹50,000")).toBeInTheDocument();
    expect(await screen.findByText(/has given benefits/)).toBeInTheDocument();
    expect(await screen.findByText("Gujarat")).toBeInTheDocument();
    expect(screen.getByText("Dealers")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Switch off" }));
    expect(await screen.findByText(/Scheme switched off/)).toBeInTheDocument();
    expect(mockDb.schemes.find((scheme) => scheme.id === mockSchemeId(1))?.is_active).toBe(false);
  });

  it("[SCHM-003] shows a dealer where it stands in a period scheme", async () => {
    signInAs("dealer");
    show(<SchemeDetail schemeId={mockSchemeId(4)} />);
    expect(await screen.findByRole("heading", { name: "Where you stand" })).toBeInTheDocument();
    expect(await screen.findByText(/of ₹5,00,000/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Who it's for" })).not.toBeInTheDocument();
  });
});

describe("[SCHM-004] CreditsList", () => {
  afterEach(reset);

  it("shows a dealer its credits to use, and when they run out", async () => {
    signInAs("dealer");
    show(<CreditsList />);
    expect(await screen.findByText("₹3,000")).toBeInTheDocument();
    expect(screen.getByText("2% of a later order")).toBeInTheDocument();
    expect(screen.getAllByText(/use by/)).toHaveLength(2);
    await waitFor(() => {
      expect(screen.queryByText("Used")).not.toBeInTheDocument();
    });
  });
});
