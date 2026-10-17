import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { getComplaint } from "@/features/complaints/api/complaints.api";
import { complaintHistoryEntry } from "@/features/complaints/lib/complaint-labels";
import { addHoliday, listHolidays, removeHoliday } from "@/features/masters/api/holidays.api";
import { HolidaysPanel, holidayProblems } from "@/features/masters/components/holidays-panel";
import { patchSettings } from "@/features/settings/api/settings.api";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ComplaintDetail } from "./complaint-detail";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn() }),
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

let keys = 0;
function key(): string {
  keys += 1;
  return `holidays-${String(keys)}`;
}

async function codeOf(call: Promise<unknown>): Promise<string | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? (error.code ?? null) : null;
}

/** The next day after today that isn't a Sunday, with an offset to keep tests apart. */
function aheadWeekday(offset: number): string {
  let day = shiftCalendarDay(todayInIndia(), offset);
  while (new Date(`${day}T00:00:00Z`).getUTCDay() === 0) day = shiftCalendarDay(day, 1);
  return day;
}

function nextSunday(): string {
  let day = shiftCalendarDay(todayInIndia(), 1);
  while (new Date(`${day}T00:00:00Z`).getUTCDay() !== 0) day = shiftCalendarDay(day, 1);
  return day;
}

function breached(): string {
  const complaint = mockDb.complaints.find((item) => item.sla?.response_breached === true);
  if (complaint === undefined) throw new Error("No complaint that missed its response target");
  return complaint.id;
}

describe("[MSTR-019] Holidays (rules)", () => {
  it("asks for a named day after today that isn't a Sunday", () => {
    const today = "2026-10-17";
    expect(holidayProblems({ day: "", name: "" }, today)).toEqual({
      day: "Choose the day.",
      name: "Name the holiday.",
    });
    expect(holidayProblems({ day: "2026-10-17", name: "X" }, today).day).toMatch(/Tomorrow/);
    expect(holidayProblems({ day: "2026-10-18", name: "X" }, today).day).toMatch(/Sundays/);
    expect(holidayProblems({ day: "2026-10-19", name: "Bhai Dooj" }, today)).toEqual({});
  });
});

describe("[MSTR-019] Holidays (contract)", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("lists a year, adds one ahead, and refuses the past, a Sunday, a repeat and readers", async () => {
    resetMockDb();
    writeMockRole("admin");
    expect((await listHolidays(2026)).every((holiday) => holiday.day.startsWith("2026-"))).toBe(
      true,
    );
    const day = aheadWeekday(3);
    await addHoliday({ body: { day, name: "Bhai Dooj" }, idempotencyKey: key() });
    expect(await codeOf(addHoliday({ body: { day, name: "Again" }, idempotencyKey: key() }))).toBe(
      "holiday_exists",
    );
    expect(
      await codeOf(
        addHoliday({ body: { day: todayInIndia(), name: "Today" }, idempotencyKey: key() }),
      ),
    ).toBe("holiday_in_past");
    expect(
      await codeOf(addHoliday({ body: { day: nextSunday(), name: "Sun" }, idempotencyKey: key() })),
    ).toBe("holiday_sunday");
    await removeHoliday({ day, idempotencyKey: key() });
    expect(await codeOf(removeHoliday({ day: "2026-01-26", idempotencyKey: key() }))).toBe(
      "holiday_in_past",
    );
    writeMockRole("employee");
    expect(await codeOf(addHoliday({ body: { day, name: "X" }, idempotencyKey: key() }))).toBe(
      "forbidden",
    );
  });
});

describe("[MSTR-019] HolidaysPanel", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("lists the year with remove only on days ahead, and adds one", async () => {
    resetMockDb();
    signInAs("admin");
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <HolidaysPanel canEdit />
        <Toaster />
      </>,
    );
    const year = todayInIndia().slice(0, 4);
    const list = await screen.findByRole("list", { name: `Holidays in ${year}` });
    expect(within(list).getAllByText("Past").length).toBeGreaterThan(0);
    expect(within(list).queryByRole("button", { name: "Remove Republic Day" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Add holiday" }));
    const form = await screen.findByRole("form", { name: "Add a holiday" });
    await user.type(within(form).getByLabelText("Day"), aheadWeekday(4));
    await user.type(within(form).getByLabelText("Name"), "Bhai Dooj");
    await user.click(within(form).getByRole("button", { name: "Add the holiday" }));
    expect(await screen.findByText("Holiday added")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Remove Bhai Dooj" })).toBeInTheDocument();
  });
});

describe("[CMPL-012] Escalation", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("marks a missed target for staff, and not when the setting is off", async () => {
    resetMockDb();
    writeMockRole("admin");
    const id = breached();
    expect((await getComplaint(id)).responseEscalatedAt).not.toBeNull();
    await patchSettings({ values: { complaint_escalation: "off" } });
    expect((await getComplaint(id)).responseEscalatedAt).toBeNull();
  });

  it("reads the timeline event without naming anyone", () => {
    expect(
      complaintHistoryEntry("complaint.escalated", { target: "resolution", due_at: null }).title,
    ).toBe("Resolution target missed: escalated");
    expect(complaintHistoryEntry("complaint.escalated", { target: "response" }).tone).toBe(
      "danger",
    );
  });

  it("says which target was missed on the complaint", async () => {
    resetMockDb();
    signInAs("admin");
    renderWithProviders(<ComplaintDetail complaintId={breached()} />);
    expect(await screen.findByText("Response target missed")).toBeInTheDocument();
    expect(screen.getByText(/Escalated to its owner and managers/)).toBeInTheDocument();
  });
});
