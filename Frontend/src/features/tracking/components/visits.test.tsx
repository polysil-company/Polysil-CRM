import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  acceptTrackingConsent,
  checkIn,
  checkOut,
  getTrackingConfig,
  getVisitPhotoLink,
  listMyVisits,
  uploadVisitPhoto,
} from "@/features/tracking/api/visits.api";
import type { CheckInRequest } from "@/features/tracking/api/visits.schemas";
import { isApiError } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { calendarDayOf } from "@/lib/format";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { openVisitIdOf } from "./check-in-form";
import { MyVisits } from "./my-visits";
import { photoProblem } from "./open-visit";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

/** The browser's location, as the test wants it: a fix, or a refusal. */
function stubLocation(answer: "fix" | "denied"): void {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: {
      getCurrentPosition: (
        ok: (position: {
          coords: { latitude: number; longitude: number; accuracy: number };
          timestamp: number;
        }) => void,
        fail: (error: { code: number; PERMISSION_DENIED: number }) => void,
      ) => {
        if (answer === "denied") {
          fail({ code: 1, PERMISSION_DENIED: 1 });
          return;
        }
        ok({
          coords: { latitude: 22.3039, longitude: 70.8022, accuracy: 12 },
          timestamp: Date.now(),
        });
      },
    },
  });
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

async function codeOf(call: Promise<unknown>): Promise<string | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? (error.code ?? null) : null;
}

function atPlace(place: string): CheckInRequest {
  const now = new Date().toISOString();
  return {
    id: createRequestId(),
    lead_id: null,
    partner_id: null,
    place_name: place,
    at: now,
    sent_at: now,
    lat: 22.3,
    lng: 70.8,
    accuracy_m: 10,
  };
}

describe("[TRK-003] Checking in (contract)", () => {
  afterEach(reset);

  it("asks for consent, checks in once, and names the open visit", async () => {
    reset();
    writeMockRole("employee");
    const config = await getTrackingConfig();
    expect(config).toMatchObject({ trackingAllowed: true, consent: { accepted: false } });
    expect(await codeOf(checkIn({ body: atPlace("Office"), idempotencyKey: "a" }))).toBe(
      "consent_required",
    );
    await acceptTrackingConsent({ version: config.consent.requiredVersion, idempotencyKey: "b" });
    expect((await getTrackingConfig()).consent.accepted).toBe(true);

    const body = atPlace("Taluka office");
    const visit = await checkIn({ body, idempotencyKey: "c" });
    expect(visit).toMatchObject({ label: "Taluka office", checkoutAt: null });
    expect((await checkIn({ body, idempotencyKey: "d" })).id).toBe(visit.id);
    const second = await checkIn({ body: atPlace("Elsewhere"), idempotencyKey: "e" }).catch(
      (caught: unknown) => caught,
    );
    expect(openVisitIdOf(second)).toBe(visit.id);
    expect(await codeOf(checkIn({ body: atPlace(" "), idempotencyKey: "f" }))).toBe(
      "validation_error",
    );
  });

  it("refuses a role that doesn't track", async () => {
    reset();
    writeMockRole("qa_manager");
    expect((await getTrackingConfig()).trackingAllowed).toBe(false);
    expect(await codeOf(checkIn({ body: atPlace("Office"), idempotencyKey: "g" }))).toBe(
      "forbidden",
    );
  });
});

describe("[TRK-004] Photos and check-out (contract)", () => {
  afterEach(reset);

  it("takes up to three photos, opens one, then checks out once", async () => {
    reset();
    writeMockRole("employee");
    mockDb.trackingConsent.set(mockMeFor("employee").data.id, "v1");
    const visit = await checkIn({ body: atPlace("Dealer meet"), idempotencyKey: "h" });
    const photo = (name: string): File => new File(["jpeg"], name, { type: "image/jpeg" });
    const first = await uploadVisitPhoto({
      visitId: visit.id,
      file: photo("1.jpg"),
      idempotencyKey: "i",
    });
    await uploadVisitPhoto({ visitId: visit.id, file: photo("2.jpg"), idempotencyKey: "j" });
    await uploadVisitPhoto({ visitId: visit.id, file: photo("3.jpg"), idempotencyKey: "k" });
    expect(
      await codeOf(
        uploadVisitPhoto({ visitId: visit.id, file: photo("4.jpg"), idempotencyKey: "l" }),
      ),
    ).toBe("photo_limit");
    expect((await getVisitPhotoLink(visit.id, first.id)).url).not.toBe("");

    const now = new Date().toISOString();
    const closed = await checkOut({
      visitId: visit.id,
      body: {
        at: now,
        sent_at: now,
        lat: 22.3,
        lng: 70.8,
        accuracy_m: 9,
        outcome: "met",
        note: " Good ",
      },
      idempotencyKey: "m",
    });
    expect(closed).toMatchObject({ outcome: "met", note: "Good", photoCount: 3 });
    expect(
      await codeOf(
        checkOut({
          visitId: visit.id,
          body: {
            at: now,
            sent_at: now,
            lat: 22.3,
            lng: 70.8,
            accuracy_m: 9,
            outcome: "met",
            note: null,
          },
          idempotencyKey: "n",
        }),
      ),
    ).toBe("visit_closed");
    const day = await listMyVisits({ date: calendarDayOf(visit.checkinAt), cursor: null });
    expect(day.items.map((item) => item.id)).toEqual([visit.id]);
  });

  it("checks a photo before sending it", () => {
    expect(photoProblem({ size: 1000, type: "image/gif" })).toMatch(/JPEG, PNG/);
    expect(photoProblem({ size: 11 * 1024 * 1024, type: "image/png" })).toMatch(/10 MB/);
    expect(photoProblem({ size: 1000, type: "image/webp" })).toBeNull();
  });
});

describe("[TRK-005] MyVisits", () => {
  afterEach(reset);

  it("consents, checks in at a place, then checks out", async () => {
    reset();
    signInAs("employee");
    stubLocation("fix");
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <MyVisits />
        <Toaster />
      </>,
    );
    expect(await screen.findByText("No visits yet today")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Check in" }));
    await user.click(await screen.findByRole("button", { name: "I agree" }));
    const form = await screen.findByRole("form", { name: "Check in" });
    await user.click(within(form).getByRole("button", { name: "Another place" }));
    await user.type(within(form).getByLabelText("Place"), "Taluka office");
    await user.click(within(form).getByRole("button", { name: "Locate me" }));
    expect(await within(form).findByText(/to within 12 m/)).toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "Check in" }));
    expect(await screen.findByText("Checked in", { selector: "[data-title]" })).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Check out" }));
    const out = await screen.findByRole("form", { name: "Check out" });
    await user.click(within(out).getByRole("radio", { name: "Met" }));
    await user.click(within(out).getByRole("button", { name: "Locate me" }));
    await within(out).findByText(/to within 12 m/);
    await user.click(within(out).getByRole("button", { name: "Check out" }));
    const list = await screen.findByRole("list", { name: "Visits" });
    await waitFor(() => {
      expect(within(list).getByText("Met")).toBeInTheDocument();
    });
  });

  it("says what to do when location is blocked", async () => {
    reset();
    signInAs("employee");
    mockDb.trackingConsent.set(mockMeFor("employee").data.id, "v1");
    stubLocation("denied");
    const user = userEvent.setup();
    renderWithProviders(<MyVisits />);
    await user.click(await screen.findByRole("button", { name: "Check in" }));
    const form = await screen.findByRole("form", { name: "Check in" });
    await user.click(within(form).getByRole("button", { name: "Locate me" }));
    expect(await within(form).findByText(/Location is blocked for this site/)).toBeInTheDocument();
    expect(within(form).getByRole("button", { name: "Check in" })).toBeDisabled();
  });

  it("tells a role without tracking", async () => {
    reset();
    signInAs("qa_manager");
    renderWithProviders(<MyVisits />);
    expect(await screen.findByText("Your role doesn't record visits")).toBeInTheDocument();
  });
});
