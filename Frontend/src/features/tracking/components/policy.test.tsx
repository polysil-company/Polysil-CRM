import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  getTrackingPolicy,
  listViewLog,
  putTrackingPolicy,
} from "@/features/tracking/api/policy.api";
import type { PolicyRequest } from "@/features/tracking/api/policy.schemas";
import { getRoute, getTeamLatest } from "@/features/tracking/api/tracking.api";
import { acceptTrackingConsent, getTrackingConfig } from "@/features/tracking/api/visits.api";
import {
  draftOf,
  policyProblems,
  requestOf,
  workDaysText,
} from "@/features/tracking/lib/policy-form";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { TrackingSettings } from "./tracking-settings";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
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

const TOMORROW = shiftCalendarDay(todayInIndia(), 1);

async function version(overrides: Partial<PolicyRequest> = {}): Promise<PolicyRequest> {
  const current = await getTrackingPolicy();
  return {
    ...requestOf(draftOf(current)),
    effective_from: `${TOMORROW}T06:00:00+05:30`,
    ...overrides,
  };
}

describe("[TRK-006] The new-version form's rules", () => {
  it("starts tomorrow from the policy in force, and checks every field", async () => {
    reset();
    const policy = await getTrackingPolicy();
    const draft = draftOf(policy, "2026-10-18");
    expect(draft.effectiveFrom).toBe("2026-10-19T00:00");
    expect(requestOf(draft).effective_from).toBe("2026-10-19T00:00:00+05:30");
    const now = Date.parse("2026-10-18T12:00:00+05:30");
    expect(policyProblems(draft, now)).toEqual({});
    expect(
      Object.keys(
        policyProblems(
          {
            ...draft,
            effectiveFrom: "2026-10-17T09:00",
            intervalSeconds: "5",
            distanceFilterM: "-1",
            retentionDays: "9999",
            workEnd: "08:00",
            workDays: [],
            consentVersion: "v 2",
            consentText: " ",
          },
          now,
        ),
      ).sort(),
    ).toEqual(
      [
        "consentText",
        "consentVersion",
        "distanceFilterM",
        "effectiveFrom",
        "intervalSeconds",
        "retentionDays",
        "workDays",
        "workEnd",
      ].sort(),
    );
  });

  it("names the working days in words", () => {
    expect(workDaysText([1, 2, 3, 4, 5, 6])).toBe("Monday to Saturday");
    expect(workDaysText([5, 1, 3])).toBe("Monday, Wednesday and Friday");
    expect(workDaysText([1, 2, 3, 4, 5, 6, 7])).toBe("Every day");
  });
});

describe("[TRK-006] Tracking policy (contract)", () => {
  afterEach(reset);

  it("adds a version, refuses the same start, the past and those without masters edit", async () => {
    reset();
    const saved = await putTrackingPolicy({
      body: await version({ interval_seconds: 300 }),
      idempotencyKey: "a",
    });
    expect(saved.intervalSeconds).toBe(300);
    expect((await getTrackingPolicy()).intervalSeconds).toBe(120);
    expect(await codeOf(putTrackingPolicy({ body: await version(), idempotencyKey: "b" }))).toBe(
      "policy_exists",
    );
    expect(
      await codeOf(
        putTrackingPolicy({
          body: await version({ effective_from: "2026-01-01T00:00:00+05:30" }),
          idempotencyKey: "c",
        }),
      ),
    ).toBe("validation_error");
    writeMockRole("employee");
    expect(await codeOf(putTrackingPolicy({ body: await version(), idempotencyKey: "d" }))).toBe(
      "forbidden",
    );
  });

  it("asks everyone to consent again when the consent version changes", async () => {
    reset();
    writeMockRole("employee");
    await acceptTrackingConsent({ version: "v1", idempotencyKey: "e" });
    expect((await getTrackingConfig()).consent.accepted).toBe(true);
    writeMockRole("admin");
    await putTrackingPolicy({
      body: await version({
        effective_from: new Date(Date.now() - 60_000).toISOString(),
        consent_version: "v2",
        consent_text: "New text from HR.",
      }),
      idempotencyKey: "f",
    });
    writeMockRole("employee");
    const config = await getTrackingConfig();
    expect(config.consent).toMatchObject({ requiredVersion: "v2", accepted: false });
    expect(config.consent.text).toBe("New text from HR.");
  });
});

describe("[TRK-007] View log (contract)", () => {
  afterEach(reset);

  it("records looks at the team map and a route, and shows them to Admin only", async () => {
    reset();
    await getTeamLatest();
    await getRoute({ userId: "usr-201", date: shiftCalendarDay(todayInIndia(), -1) });
    const log = await listViewLog({ subjectUserId: null, cursor: null });
    expect(log.items[0]).toMatchObject({ what: "route", subject: { id: "usr-201" } });
    expect(log.items[1]).toMatchObject({ what: "team", subject: null });
    const ravi = await listViewLog({ subjectUserId: "usr-201", cursor: null });
    expect(ravi.items.every((row) => row.subject?.id === "usr-201")).toBe(true);
    writeMockRole("district_manager");
    expect((await listViewLog({ subjectUserId: null, cursor: null })).items).toHaveLength(0);
  });
});

describe("[TRK-006] TrackingSettings", () => {
  afterEach(reset);

  it("shows the policy in words and saves a new version after fixing a field", async () => {
    reset();
    signInAs("admin");
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <TrackingSettings />
        <Toaster />
      </>,
    );
    expect(await screen.findByText(/monday to saturday/)).toBeInTheDocument();
    expect(screen.getByText("90 days")).toBeInTheDocument();
    expect(screen.getByText("Optional")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save a new version" }));
    const form = await screen.findByRole("form", { name: "Save a new version" });
    const interval = within(form).getByLabelText("Seconds between locations");
    await user.clear(interval);
    await user.type(interval, "5");
    await user.click(within(form).getByRole("button", { name: "Save version" }));
    expect(await within(form).findByText(/from 15 to 3600/)).toBeInTheDocument();
    await user.clear(interval);
    await user.type(interval, "300");
    await user.click(within(form).getByRole("button", { name: "Save version" }));
    expect(await screen.findByText("New version saved")).toBeInTheDocument();
  });

  it("lists who looked, and filters by person", async () => {
    reset();
    signInAs("admin");
    const user = userEvent.setup();
    renderWithProviders(<TrackingSettings />, { searchParams: "?tab=views" });
    const list = await screen.findByRole("list", { name: "Who looked, newest first" });
    expect(within(list).getAllByRole("listitem").length).toBeGreaterThan(1);
    expect(within(list).getByText(/the team map/)).toBeInTheDocument();
    await user.click(screen.getByLabelText("Whose location"));
    await user.click(await screen.findByRole("option", { name: "Ravi Patel" }));
    await waitFor(() => {
      expect(
        within(screen.getByRole("list", { name: "Who looked, newest first" })).queryByText(
          /the team map/,
        ),
      ).not.toBeInTheDocument();
    });
  });
});
