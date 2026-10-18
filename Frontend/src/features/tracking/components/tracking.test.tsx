import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getRoute, getTeamLatest } from "@/features/tracking/api/tracking.api";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { RouteDay } from "./route-day";
import { TeamMap } from "./team-map";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

async function statusOf(call: Promise<unknown>): Promise<number | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? error.status : null;
}

const YESTERDAY = shiftCalendarDay(todayInIndia(), -1);

describe("[TRK-001] Team map (contract)", () => {
  afterEach(reset);

  it("gives a manager the whole team, a field officer themselves, and others nothing", async () => {
    reset();
    const team = await getTeamLatest();
    expect(team).toHaveLength(6);
    expect(team.map((person) => person.state)).toEqual(
      expect.arrayContaining(["on_duty", "stale", "off_duty"]),
    );
    expect(team.find((person) => person.state === "off_duty")?.position).toBeNull();
    expect(team.some((person) => person.isMock)).toBe(true);

    writeMockRole("employee");
    expect((await getTeamLatest()).map((person) => person.id)).toEqual([
      mockMeFor("employee").data.id,
    ]);
    writeMockRole("qa_manager");
    expect(await statusOf(getTeamLatest())).toBe(403);
  });
});

describe("[TRK-002] Route of a day (contract)", () => {
  afterEach(reset);

  it("draws a past day with its stops and visits, and nothing for a day ahead", async () => {
    reset();
    const route = await getRoute({ userId: "usr-201", date: YESTERDAY });
    expect(route.points.length).toBeGreaterThan(20);
    expect(route.stops.length).toBeGreaterThan(0);
    expect(route.visits.length).toBeGreaterThan(0);
    expect(route.distanceKm).toBeGreaterThan(0);
    expect(route.droppedPoints).toBe(7);
    const times = route.points.map((point) => point.at);
    expect(times).toEqual([...times].sort());

    const ahead = await getRoute({
      userId: "usr-201",
      date: shiftCalendarDay(todayInIndia(), 2),
    });
    expect(ahead.points).toHaveLength(0);
  });

  it("answers 404 for someone outside the team", async () => {
    reset();
    writeMockRole("employee");
    expect(await statusOf(getRoute({ userId: "usr-201", date: YESTERDAY }))).toBe(404);
  });
});

describe("[TRK-001] TeamMap", () => {
  afterEach(reset);

  it("lists each person in words: state, battery, an open visit and a fake location", async () => {
    reset();
    signInAs("admin");
    renderWithProviders(<TeamMap />);
    const team = await screen.findByRole("list", { name: "Team" });
    expect(within(team).getAllByRole("link")).toHaveLength(6);
    expect(within(team).getAllByText("On duty").length).toBeGreaterThan(0);
    expect(within(team).getByText("Not heard from")).toBeInTheDocument();
    expect(within(team).getByText("Off duty")).toBeInTheDocument();
    expect(within(team).getByText("Fake location")).toBeInTheDocument();
    expect(within(team).getByText(/Battery low/)).toBeInTheDocument();
    expect(within(team).getByText(/On a visit to/)).toBeInTheDocument();
    expect(within(team).getByRole("link", { name: /Ravi Patel/ })).toHaveAttribute(
      "href",
      "/team-map/usr-201",
    );
    expect(screen.getByText(/5 of 6 on duty/)).toBeInTheDocument();
  });

  it("says so when the role has no tracking", async () => {
    reset();
    signInAs("qa_manager");
    renderWithProviders(<TeamMap />);
    expect(await screen.findByText("Your role has no tracking")).toBeInTheDocument();
  });
});

describe("[TRK-002] RouteDay", () => {
  afterEach(reset);

  it("shows a day's figures, duty and visits, and moves between days", async () => {
    reset();
    signInAs("admin");
    const user = userEvent.setup();
    const urls: string[] = [];
    renderWithProviders(<RouteDay userId="usr-201" />, {
      searchParams: `?date=${YESTERDAY}`,
      onUrlChange: (query) => {
        urls.push(query);
      },
    });
    expect(await screen.findByRole("heading", { name: "Ravi Patel" })).toBeInTheDocument();
    expect(screen.getByText("Distance")).toBeInTheDocument();
    const stops = screen.getByRole("list", { name: "Visits and stops" });
    expect(within(stops).getAllByText("Visit").length).toBeGreaterThan(0);
    expect(within(stops).getAllByRole("link").length).toBeGreaterThan(0);
    expect(screen.getByText(/left out for poor accuracy/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "The day before" }));
    await waitFor(() => {
      expect(urls.at(-1)).toContain(`date=${shiftCalendarDay(YESTERDAY, -1)}`);
    });
  });

  it("says when nothing was tracked, and doesn't go past today", async () => {
    reset();
    signInAs("admin");
    renderWithProviders(<RouteDay userId="usr-204" />);
    expect(await screen.findByText("No duty this day")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "The day after" })).toBeDisabled();
  });
});
