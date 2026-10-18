import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FarmersToPortal } from "@/components/layout/farmers-to-portal";
import { PortalShell } from "@/components/layout/portal-shell";
import { Toaster } from "@/components/ui/sonner";
import { getLeadStats } from "@/features/leads/api/leads.api";
import {
  createPortalRating,
  getPortalMe,
  listPortalComplaints,
  listPortalOrders,
  listPortalQuotations,
  listPortalRatings,
  patchPortalConsent,
} from "@/features/portal/api/portal.api";
import { patchSettings } from "@/features/settings/api/settings.api";
import { registerAccessTokenProvider } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { writeMockConsumerMobile, writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { mockConsumerMe } from "@/mocks/handlers/portal";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { PortalHome } from "./portal-home";

const router = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ replace: router.replace, push: vi.fn(), prefetch: vi.fn() }),
}));

/** A farmer whose direct order has shipped and is not yet rated. */
const HITESH = "+916798273387";
const HITESH_ORDER = "SO/GJ/2026-27/00005";
/** A farmer whose complaint is closed and was rated with an officer. */
const GANPAT = "+916570561082";
/** A farmer whose order went through a dealer. */
const HANSA = "+917246451095";

let keys = 0;
function key(): string {
  keys += 1;
  return `portal-${String(keys)}`;
}

async function codeOf(call: Promise<unknown>): Promise<string | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? (error.code ?? null) : null;
}

/** Switch the portal on as Admin. Previewing a role ends any farmer's session, so do it first. */
async function switchPortalOn(): Promise<void> {
  writeMockRole("admin");
  await patchSettings({ values: { consumer_portal: "on" } });
}

function signInAsFarmer(mobile: string): void {
  writeMockConsumerMobile(mobile);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockConsumerMe())));
}

function reset(): void {
  // The portal shell loads the session store, which connects the client to a session.
  // Unit tests run without one, as everywhere else.
  registerAccessTokenProvider(null);
  resetMockDb();
  writeMockConsumerMobile(null);
  writeMockRole("admin");
  router.replace.mockClear();
}

describe("[FARM-001] The farmers' portal (contract)", () => {
  afterEach(reset);

  it("is off by default, for farmers only, and fences a farmer out of the rest", async () => {
    reset();
    expect(await codeOf(getPortalMe())).toBe("not_a_consumer");
    signInAsFarmer(HITESH);
    expect(await codeOf(getPortalMe())).toBe("portal_off");
    expect(await codeOf(getLeadStats())).toBe("consumer_not_allowed");
  });

  it("gives the farmer their own record once it is on, without a dealer's totals", async () => {
    reset();
    await switchPortalOn();
    signInAsFarmer(HITESH);
    expect((await getPortalMe()).mobile).toBe(HITESH);
    const orders = await listPortalOrders();
    expect(orders.map((order) => order.number)).toEqual([HITESH_ORDER]);
    expect(orders[0]?.total).not.toBeNull();
    expect(orders[0]?.dispatches.length).toBeGreaterThan(0);

    signInAsFarmer(HANSA);
    const viaDealer = await listPortalOrders();
    expect(viaDealer[0]?.total).toBeNull();
    expect((await listPortalQuotations()).every((quotation) => quotation.total === null)).toBe(
      true,
    );
  });
});

describe("[FARM-002] Consent from the portal (contract)", () => {
  afterEach(reset);

  it("records consent on the portal, keeps the first date, and withdraws it", async () => {
    reset();
    await switchPortalOn();
    signInAsFarmer(HITESH);
    const given = await patchPortalConsent({ consentGiven: true, idempotencyKey: key() });
    expect(given.consentChannel).toBe("portal");
    const again = await patchPortalConsent({ consentGiven: true, idempotencyKey: key() });
    expect(again.consentGivenAt).toBe(given.consentGivenAt);
    const withdrawn = await patchPortalConsent({ consentGiven: false, idempotencyKey: key() });
    expect(withdrawn).toMatchObject({ consentGivenAt: null, consentChannel: null });
  });
});

describe("[FARM-003] Rating from the portal (contract)", () => {
  afterEach(reset);

  it("rates a shipped order once, and refuses what can't be rated", async () => {
    reset();
    await switchPortalOn();
    signInAsFarmer(HITESH);
    const saved = await createPortalRating({
      body: { target: "installation", order_no: HITESH_ORDER, score: 5, comment: "Very neat" },
      idempotencyKey: key(),
    });
    expect(saved).toMatchObject({ enteredVia: "portal", comment: "Very neat", score: 5 });
    expect(
      await codeOf(
        createPortalRating({
          body: { target: "installation", order_no: HITESH_ORDER, score: 3 },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("rating_exists");
    expect((await listPortalRatings()).map((rating) => rating.orderNo)).toEqual([HITESH_ORDER]);
    expect(
      await codeOf(
        createPortalRating({
          body: { target: "installation", order_no: "SO/GJ/2026-27/99999", score: 3 },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("not_found");

    signInAsFarmer(GANPAT);
    const closed = (await listPortalComplaints()).find(
      (complaint) => complaint.status === "closed",
    );
    expect(closed).toBeDefined();
    const officer = (await listPortalRatings()).find((rating) => rating.target === "service");
    expect(officer).toMatchObject({ enteredVia: "staff", comment: null });
  });
});

describe("[FARM-001] PortalHome", () => {
  afterEach(reset);

  it("says the portal is closed while it is off", async () => {
    reset();
    signInAsFarmer(HITESH);
    renderWithProviders(<PortalHome />);
    expect(
      await screen.findByRole("heading", { name: "The portal is closed for now" }),
    ).toBeInTheDocument();
  });

  it("shows the farmer's orders and lets them rate the installation", async () => {
    reset();
    await switchPortalOn();
    signInAsFarmer(HITESH);
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <PortalHome />
        <Toaster />
      </>,
    );
    expect(await screen.findByRole("heading", { name: /Namaste/ })).toBeInTheDocument();
    const orders = await screen.findByRole("list", { name: "Your orders" });
    expect(within(orders).getByText(HITESH_ORDER)).toBeInTheDocument();
    await user.click(
      await within(orders).findByRole("button", {
        name: `Rate the installation of ${HITESH_ORDER}`,
      }),
    );
    const form = await screen.findByRole("form", {
      name: `Rate the installation of ${HITESH_ORDER}`,
    });
    await user.click(within(form).getByRole("radio", { name: "5 stars, Very good" }));
    await user.click(within(form).getByRole("button", { name: "Send rating" }));
    expect(await screen.findByText("Thank you for your rating")).toBeInTheDocument();
    expect(await within(orders).findByText("Your rating")).toBeInTheDocument();
  });

  it("lets the farmer agree to be contacted", async () => {
    reset();
    await switchPortalOn();
    signInAsFarmer(HITESH);
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <PortalHome />
        <Toaster />
      </>,
    );
    await user.click(await screen.findByRole("button", { name: "Yes, contact me" }));
    expect(await screen.findByText(/You agreed to be contacted on/)).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Stop updates" }, { timeout: 4000 }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("shows a complaint rated with an officer, with no button to rate it again", async () => {
    reset();
    await switchPortalOn();
    signInAsFarmer(GANPAT);
    renderWithProviders(<PortalHome />);
    const complaints = await screen.findByRole("list", { name: "Your complaints" });
    expect(await within(complaints).findByText("Rated with our officer")).toBeInTheDocument();
    expect(within(complaints).queryByRole("button", { name: /Rate/ })).not.toBeInTheDocument();
  });
});

describe("[FARM-001] PortalShell and FarmersToPortal", () => {
  afterEach(reset);

  it("points staff back to the main app", async () => {
    reset();
    server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor("admin"))));
    renderWithProviders(
      <PortalShell>
        <p>The farmer&apos;s record</p>
      </PortalShell>,
    );
    expect(
      await screen.findByRole("heading", { name: "This is the farmers' portal" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("The farmer's record")).not.toBeInTheDocument();
  });

  it("sends a farmer who lands in the main app to the portal", async () => {
    reset();
    signInAsFarmer(HITESH);
    renderWithProviders(
      <FarmersToPortal>
        <p>The staff app</p>
      </FarmersToPortal>,
    );
    await waitFor(() => {
      expect(router.replace).toHaveBeenCalledWith("/portal");
    });
    expect(screen.queryByText("The staff app")).not.toBeInTheDocument();
  });
});
