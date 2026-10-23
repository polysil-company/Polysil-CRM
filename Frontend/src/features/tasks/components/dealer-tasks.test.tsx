import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { visibleNavSections } from "@/components/layout/navigation";
import { Toaster } from "@/components/ui/sonner";
import { patchSettings } from "@/features/settings/api/settings.api";
import {
  completeTask,
  createTask,
  listTaskAssignees,
  listTasks,
  patchTask,
} from "@/features/tasks/api/tasks.api";
import { dealerTaskParams, useDealerTasksOn } from "@/features/tasks/hooks/use-dealer-tasks";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { DealerTasks } from "./dealer-tasks";
import { NewTaskDialog } from "./new-task-dialog";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

let keys = 0;
function key(): string {
  keys += 1;
  return `dealer-tasks-${String(keys)}`;
}

async function codeOf(call: Promise<unknown>): Promise<string | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? (error.code ?? null) : null;
}

const DEALER_USER = mockMeFor("dealer").data;

async function switchOn(): Promise<void> {
  writeMockRole("admin");
  await patchSettings({ values: { tasks_for_dealers: "on" } });
}

async function giveDealerATask(title: string): Promise<string> {
  writeMockRole("district_manager");
  const task = await createTask({
    body: {
      title,
      task_type: "call",
      due_at: "2026-10-20",
      assigned_to: DEALER_USER.id,
    },
    idempotencyKey: key(),
  });
  return task.id;
}

describe("[TASK-009] Tasks for dealers (contract)", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("refuses a dealer every tasks route while the setting is off", async () => {
    resetMockDb();
    writeMockRole("dealer");
    expect(await codeOf(listTasks({ ...dealerTaskParams("open"), cursor: null }))).toBe(
      "forbidden",
    );
  });

  it("offers staff the dealers' users once it is on, and lets the dealer complete only", async () => {
    resetMockDb();
    writeMockRole("district_manager");
    expect((await listTaskAssignees()).some((person) => person.kind === "partner")).toBe(false);
    await switchOn();
    writeMockRole("district_manager");
    const people = await listTaskAssignees();
    const dealer = people.find((person) => person.id === DEALER_USER.id);
    expect(dealer).toMatchObject({ kind: "partner", partner: { name: "Shah Agro Traders" } });

    const taskId = await giveDealerATask("Call the Patel farm about the drip quote");
    writeMockRole("dealer");
    const page = await listTasks({ ...dealerTaskParams("open"), cursor: null });
    expect(page.items.map((task) => task.id)).toContain(taskId);
    expect(
      await codeOf(patchTask({ taskId, body: { title: "Changed" }, idempotencyKey: key() })),
    ).toBe("forbidden");
    const done = await completeTask({
      taskId,
      body: { outcome: "Called; visiting Friday." },
      idempotencyKey: key(),
    });
    expect(done.status).toBe("done");
  });

  it("refuses a dealer a task about a lead that isn't theirs", async () => {
    resetMockDb();
    await switchOn();
    writeMockRole("district_manager");
    const lead = mockDb.leads.find((item) => item.assigned_partner?.id !== "prt-201");
    if (lead === undefined) throw new Error("No lead outside the dealer");
    expect(
      await codeOf(
        createTask({
          body: {
            title: "Visit",
            task_type: "visit",
            due_at: "2026-10-20",
            assigned_to: DEALER_USER.id,
            lead_id: lead.id,
          },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("link_not_visible_to_assignee");
  });
});

describe("[TASK-009] The dealers' Tasks item", () => {
  it("waits on its gate", () => {
    const permissions = mockPermissionsFor("dealer");
    const ids = (gates: ReadonlySet<"dealer-tasks">): string[] =>
      visibleNavSections(permissions, "partner_user", null, gates)
        .flatMap((section) => section.items)
        .map((item) => item.id);
    expect(ids(new Set())).not.toContain("dealer-tasks");
    expect(ids(new Set(["dealer-tasks"]))).toContain("dealer-tasks");
    expect(ids(new Set(["dealer-tasks"]))).not.toContain("tasks");
  });
});

describe("[TASK-009] DealerTasks", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("says tasks aren't switched on while the setting is off", async () => {
    resetMockDb();
    signInAs("dealer");
    renderWithProviders(<DealerTasks />);
    expect(await screen.findByText("Tasks aren't switched on")).toBeInTheDocument();
  });

  it("lists the dealer's tasks with Done only, and marks one done", async () => {
    resetMockDb();
    await switchOn();
    await giveDealerATask("Call the Patel farm about the drip quote");
    signInAs("dealer");
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <DealerTasks />
        <Toaster />
      </>,
    );
    const list = await screen.findByRole("list", { name: "Tasks to do" });
    const row = within(list).getByRole("listitem", { name: /Patel farm/ });
    expect(within(row).queryByRole("button", { name: /More|Actions/ })).toBeNull();
    await user.click(within(row).getByRole("button", { name: /Mark done/ }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox"), "Called; visiting Friday.");
    await user.click(within(dialog).getByRole("button", { name: /done/i }));
    expect(await screen.findByText("Nothing to do")).toBeInTheDocument();
  });
});

describe("[TASK-009] The new task dialog's Dealers group", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("groups the dealers' users once the setting is on", async () => {
    resetMockDb();
    await switchOn();
    signInAs("district_manager");
    const user = userEvent.setup();
    renderWithProviders(
      <NewTaskDialog subject={null} meId={mockMeFor("district_manager").data.id} />,
    );
    await user.click(screen.getByRole("button", { name: /New task|Add task/ }));
    await user.click(await screen.findByLabelText("For"));
    expect(await screen.findByText("Dealers")).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Bhavesh Shah · Shah Agro Traders" }),
    ).toBeInTheDocument();
  });
});

function GateProbe(): React.JSX.Element {
  return <p>{useDealerTasksOn() ? "Tasks on" : "Tasks off"}</p>;
}

describe("[TASK-009] The dealer's Tasks gate (BE-030)", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("follows the switch on /auth/me, and never asks /tasks to find out", async () => {
    const asked: string[] = [];
    server.events.on("request:start", ({ request }) => {
      asked.push(new URL(request.url).pathname);
    });
    writeMockRole("dealer");
    server.use(
      http.get(buildApiUrl("/auth/me"), () =>
        HttpResponse.json({
          data: { ...mockMeFor("dealer").data, features: { tasks_for_dealers: true } },
        }),
      ),
    );
    renderWithProviders(<GateProbe />);
    expect(await screen.findByText("Tasks on")).toBeInTheDocument();
    expect(asked.some((path) => path.endsWith("/tasks"))).toBe(false);
    server.events.removeAllListeners();
  });

  it("stays off while the switch is off", async () => {
    signInAs("dealer");
    renderWithProviders(<GateProbe />);
    expect(await screen.findByText("Tasks off")).toBeInTheDocument();
  });
});
