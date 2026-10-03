import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { MOCK_TASK_ME, MOCK_TEAM } from "@/mocks/data/tasks";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { LeadTasks } from "./lead-tasks";
import { TasksView } from "./tasks-view";

/** Unit tests have no access token, so the session is served directly for one role. */
function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

function showTasks(searchParams = ""): {
  user: ReturnType<typeof userEvent.setup>;
  onUrlChange: (queryString: string) => void;
} {
  const user = userEvent.setup();
  const onUrlChange = vi.fn<(queryString: string) => void>();
  renderWithProviders(
    <>
      <TasksView />
      <Toaster />
    </>,
    { searchParams, onUrlChange },
  );
  return { user, onUrlChange };
}

async function dueToday(): Promise<HTMLElement[]> {
  const section = await screen.findByRole("region", { name: /^Today/ });
  return within(section).getAllByRole("listitem");
}

describe("[TASK-001] My day", () => {
  afterEach(reset);

  it("shows today's tasks by time, with what is overdue from earlier on top", async () => {
    signInAs("district_manager");
    showTasks();

    const today = await dueToday();
    expect(today.length).toBeGreaterThanOrEqual(6);
    const overdue = screen.getByRole("region", { name: /^Overdue from earlier/ });
    expect(within(overdue).getAllByRole("listitem").length).toBeGreaterThanOrEqual(3);
    expect(within(overdue).getAllByText("Overdue").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText(/due today.*overdue from earlier/)).toBeInTheDocument();
  });

  it("moves to the next day and back to today, keeping the day in the URL", async () => {
    signInAs("employee");
    const { user, onUrlChange } = showTasks();
    await dueToday();

    await user.click(screen.getByRole("button", { name: "Next day" }));
    await waitFor(() => {
      expect(onUrlChange).toHaveBeenLastCalledWith(expect.stringMatching(/date=\d{4}-\d{2}-\d{2}/));
    });
    // A future day has nothing overdue.
    await waitFor(() => {
      expect(screen.queryByRole("region", { name: /^Overdue/ })).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /^Back to today/ }));
    expect(await screen.findByRole("region", { name: /^Today/ })).toBeInTheDocument();
  });

  it("marks a task done with what happened", async () => {
    signInAs("employee");
    const { user } = showTasks();
    const [first] = (await dueToday()).filter(
      (row) => within(row).queryByRole("button", { name: /^Mark done/ }) !== null,
    );
    if (first === undefined) throw new Error("Nothing open today");

    await user.click(within(first).getByRole("button", { name: /^Mark done/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Mark done" }));
    expect(await within(dialog).findByText("Say what happened.")).toBeVisible();
    await user.type(within(dialog).getByLabelText("What happened"), "Spoke to him.");
    await user.click(within(dialog).getByRole("button", { name: "Mark done" }));

    expect(await screen.findByText("Marked done", { selector: "[data-title]" })).toBeVisible();
    expect(mockDb.tasks.some((task) => task.outcome === "Spoke to him.")).toBe(true);
  });

  it("cancels a task with a reason, but not one someone else gave the user", async () => {
    signInAs("employee");
    // Two of today's open tasks: one the user gave themselves, one a manager gave them.
    const [own, given] = mockDb.tasks.filter(
      (task) =>
        task.status === "open" &&
        task.assigned_to?.id === MOCK_TASK_ME.id &&
        task.due_at.slice(0, 10) >= new Date(Date.now() - 86_400_000).toISOString().slice(0, 10),
    );
    if (own === undefined || given === undefined) throw new Error("Not enough open tasks");
    mockDb.tasks = mockDb.tasks.map((task) =>
      task.id === own.id
        ? { ...task, title: "Plan the week", assigned_by: { ...MOCK_TASK_ME } }
        : task.id === given.id
          ? {
              ...task,
              title: "Check the stock report",
              assigned_by: { id: "usr-manager", full_name: "Asha Patel" },
            }
          : task,
    );
    const { user } = showTasks();
    await dueToday();

    const givenRow = screen.getByRole("listitem", { name: /: Check the stock report$/ });
    expect(within(givenRow).getByText("Given by Asha Patel")).toBeInTheDocument();
    // Only whoever gave it may cancel it, so there is nothing in its menu to offer.
    expect(within(givenRow).queryByRole("button", { name: /^More for/ })).toBeNull();

    const ownRow = screen.getByRole("listitem", { name: /: Plan the week$/ });
    await user.click(within(ownRow).getByRole("button", { name: /^More for/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Cancel task" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Reason"), "Covered yesterday.");
    await user.click(within(dialog).getByRole("button", { name: "Cancel task" }));

    expect(await screen.findByText("Task cancelled", { selector: "[data-title]" })).toBeVisible();
    expect(mockDb.tasks.find((task) => task.id === own.id)?.cancel_reason).toBe(
      "Covered yesterday.",
    );
  });

  it("adds a task for the chosen day, with the time optional", async () => {
    signInAs("employee");
    const { user } = showTasks();
    await dueToday();

    await user.click(screen.getByRole("button", { name: "New task" }));
    const dialog = await screen.findByRole("dialog", { name: "New task" });
    await user.click(within(dialog).getByRole("button", { name: "Add task" }));
    expect(await within(dialog).findByText("Say what is to be done.")).toBeVisible();

    await user.type(within(dialog).getByLabelText("What to do"), "Send the weekly report");
    await user.click(within(dialog).getByRole("button", { name: "Add task" }));

    expect(await screen.findByText("Task added", { selector: "[data-title]" })).toBeVisible();
    await waitFor(async () => {
      const titles = (await dueToday()).map((row) => row.getAttribute("aria-label"));
      expect(titles).toContain("Follow-up: Send the weekly report");
    });
  });

  it("explains when the day could not be loaded", async () => {
    signInAs("employee");
    server.use(
      http.get(buildApiUrl("/planner"), () =>
        HttpResponse.json({ error: { code: "server_error", message: "boom" } }, { status: 500 }),
      ),
    );
    showTasks();

    expect(await screen.findByRole("button", { name: /Try again|Retry/ })).toBeInTheDocument();
  });

  it("says when the day is clear", async () => {
    signInAs("employee");
    server.use(
      http.get(buildApiUrl("/planner"), () =>
        HttpResponse.json({
          data: { date: "2026-10-03", user: null, due: [], overdue: [] },
        }),
      ),
    );
    showTasks();

    expect(await screen.findByText(/A clear day|Nothing due/)).toBeInTheDocument();
  });
});

describe("[TASK-002] Team day", () => {
  afterEach(reset);

  it("is offered to managers only", async () => {
    signInAs("employee");
    showTasks();
    await dueToday();

    expect(screen.queryByRole("radio", { name: "Team" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Team" })).not.toBeInTheDocument();
  });

  it("lists each person below the manager, and opens their day", async () => {
    signInAs("district_manager");
    const { user, onUrlChange } = showTasks("?view=team");

    const team = await screen.findByRole("list", { name: /^Your team/ });
    expect(within(team).getAllByRole("listitem")).toHaveLength(MOCK_TEAM.length);
    const person = MOCK_TEAM[1];
    await user.click(
      within(team).getByRole("button", { name: new RegExp(`^${person?.full_name ?? ""}:`) }),
    );

    await waitFor(() => {
      expect(onUrlChange).toHaveBeenLastCalledWith(expect.stringContaining("user="));
    });
    expect(
      await screen.findByRole("heading", { name: `${person?.full_name ?? ""}'s day` }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to team" }));
    expect(await screen.findByRole("list", { name: /^Your team/ })).toBeInTheDocument();
  });
});

describe("[TASK-003] LeadTasks", () => {
  afterEach(reset);

  function leadWithTasks(): { id: string; name: string } {
    const task = mockDb.tasks.find((item) => item.lead !== null && item.status === "open");
    const lead = mockDb.leads.find((item) => item.id === task?.lead?.id);
    if (lead === undefined) throw new Error("No lead with tasks");
    return { id: lead.id, name: lead.farmer_name };
  }

  it("shows what is still to do on the lead, then what was done", async () => {
    signInAs("admin");
    const lead = leadWithTasks();
    renderWithProviders(<LeadTasks leadId={lead.id} leadName={lead.name} merged={false} />);

    const todo = await screen.findByRole("region", { name: "To do" });
    expect(within(todo).getAllByRole("listitem").length).toBeGreaterThan(0);
    // On the lead's own page, a task does not link back to it.
    expect(within(todo).queryByRole("link", { name: new RegExp(lead.name) })).toBeNull();
  });

  it("adds a meeting about the lead, naming the kind of meeting", async () => {
    signInAs("admin");
    const user = userEvent.setup();
    const lead = leadWithTasks();
    renderWithProviders(
      <>
        <LeadTasks leadId={lead.id} leadName={lead.name} merged={false} />
        <Toaster />
      </>,
    );
    await screen.findByRole("region", { name: "To do" });

    await user.click(screen.getByRole("button", { name: "Add task" }));
    const dialog = await screen.findByRole("dialog", { name: "Add a task" });
    expect(within(dialog).getByText(`About ${lead.name}.`)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("What to do"), "Survey the farm");
    await user.click(within(dialog).getByRole("combobox", { name: "Kind" }));
    await user.click(await screen.findByRole("option", { name: "Meeting" }));
    await user.click(within(dialog).getByRole("button", { name: "Add task" }));
    expect(await within(dialog).findByText("Choose the kind of meeting.")).toBeVisible();

    await user.click(within(dialog).getByRole("combobox", { name: "Kind of meeting" }));
    await user.click(await screen.findByRole("option", { name: "Survey & Design" }));
    await user.click(within(dialog).getByRole("button", { name: "Add task" }));

    expect(await screen.findByText("Task added", { selector: "[data-title]" })).toBeVisible();
    const created = mockDb.tasks.find((task) => task.title === "Survey the farm");
    expect(created).toMatchObject({
      task_type: "meeting",
      lead: { id: lead.id },
      meeting_type: { name: "Survey & Design" },
    });
  });

  it("offers no new task on a merged lead", async () => {
    signInAs("admin");
    const lead = leadWithTasks();
    renderWithProviders(<LeadTasks leadId={lead.id} leadName={lead.name} merged />);

    await screen.findByRole("region", { name: "To do" });
    expect(screen.queryByRole("button", { name: "Add task" })).not.toBeInTheDocument();
  });
});
