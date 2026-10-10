import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { PersonDetail } from "./person-detail";
import { EditPerson, NewPerson } from "./person-pages";
import { UsersList } from "./users-list";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), notFound: vi.fn() }));

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

function idOf(name: string): string {
  const person = mockDb.users.find((user) => user.full_name === name);
  if (person === undefined) throw new Error(`No ${name}`);
  return person.id;
}

async function dialogClosed(): Promise<void> {
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
}

/** What an input holds now, read without a type assertion. */
function valueOf(element: HTMLElement): string {
  if (!(element instanceof HTMLInputElement)) throw new Error("Not an input");
  return element.value;
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
  push.mockReset();
}

describe("[ADMN-001] UsersList", () => {
  beforeEach(reset);
  afterEach(reset);

  it("lists people with how they sign in, their role, place and state", async () => {
    signInAs("admin");
    show(<UsersList />);
    const list = await screen.findByRole("list", { name: "People" });
    const ravi = within(list).getByRole("link", {
      name: /^Ravi Joshi, Field Officer, Rajkot District/,
    });
    expect(ravi).toHaveTextContent("ravi.joshi@polysil.in");
    expect(ravi).toHaveTextContent(/open leads/);
    expect(
      within(list).getByRole("link", { name: /Vijay Chaudhary.*deactivated/ }),
    ).toHaveTextContent("Deactivated");
    expect(within(list).getByRole("link", { name: /^Hansa Gohil/ })).toHaveTextContent(
      "Temporary password",
    );
    expect(screen.getByRole("link", { name: "New person" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Download Excel/ })).toBeInTheDocument();
  });

  it("filters to partner users from the URL", async () => {
    signInAs("admin");
    show(<UsersList />, "type=partner_user");
    const list = await screen.findByRole("list", { name: "People" });
    const rows = within(list).getAllByRole("link");
    expect(rows.length).toBeGreaterThan(0);
    expect(within(list).queryByText(/@polysil\.in/)).not.toBeInTheDocument();
  });

  it("offers no New person to whoever may only look", async () => {
    signInAs("admin");
    const permissions = mockMeFor("admin").data.permissions?.map((grant) =>
      grant.module === "users" ? { ...grant, actions: ["view"] } : grant,
    );
    server.use(
      http.get(buildApiUrl("/auth/me"), () =>
        HttpResponse.json({ data: { ...mockMeFor("admin").data, permissions } }),
      ),
    );
    show(<UsersList />);
    await screen.findByRole("list", { name: "People" });
    expect(screen.queryByRole("link", { name: "New person" })).not.toBeInTheDocument();
  });
});

describe("[ADMN-002] PersonDetail", () => {
  beforeEach(reset);
  afterEach(reset);

  it("shows how they sign in, the lockout, their role and place, and every action", async () => {
    signInAs("admin");
    const user = show(<PersonDetail userId={idOf("Ravi Joshi")} />);
    expect(await screen.findByRole("heading", { name: "Ravi Joshi" })).toBeInTheDocument();
    expect(screen.getByText("Locked out", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("ravi.joshi@polysil.in")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Territories" })).toHaveTextContent("Rajkot");

    await user.click(await screen.findByRole("button", { name: "More actions for Ravi Joshi" }));
    expect(
      await screen.findByRole("menuitem", { name: "Set a temporary password" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Unlock sign-in" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Hand over leads and tasks" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Deactivate" })).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Delete (hand over leads first)" }),
    ).toHaveAttribute("aria-disabled", "true");
  });

  it("on your own row, offers no deactivate, delete or hand-over to yourself", async () => {
    signInAs("admin");
    const user = show(<PersonDetail userId="usr-001" />);
    expect(await screen.findByRole("heading", { name: "Aarav Desai" })).toBeInTheDocument();
    expect(await screen.findByText("You")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "More actions for Aarav Desai" }));
    await screen.findByRole("menuitem", { name: "Sign out everywhere" });
    expect(screen.queryByRole("menuitem", { name: "Deactivate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^Delete/ })).not.toBeInTheDocument();
  });

  it("[ADMN-005] sets a temporary password and shows it once", async () => {
    signInAs("admin");
    const user = show(<PersonDetail userId={idOf("Bharat Vaghela")} />);
    await user.click(
      await screen.findByRole("button", { name: "More actions for Bharat Vaghela" }),
    );
    await user.click(await screen.findByRole("menuitem", { name: "Set a temporary password" }));
    const dialog = await screen.findByRole("dialog");
    const field = within(dialog).getByLabelText("Temporary password");
    const suggested = valueOf(field);
    expect(suggested).toMatch(/^[\w]{4}-[\w]{4}-[\w]{4}-[\w]{4}$/);
    await user.click(within(dialog).getByRole("button", { name: "Set the password" }));
    expect(await within(dialog).findByText("New temporary password set")).toBeInTheDocument();
    expect(within(dialog).getByText(suggested)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Done" }));
    await dialogClosed();
    expect(await screen.findByText("Temporary password", { selector: "span" })).toBeInTheDocument();
  });

  it("[ADMN-006] hands a leaver's work over, then deactivates them", async () => {
    signInAs("admin");
    const user = show(<PersonDetail userId={idOf("Kajal Solanki")} />);
    await user.click(await screen.findByRole("button", { name: "More actions for Kajal Solanki" }));
    await user.click(await screen.findByRole("menuitem", { name: "Hand over leads and tasks" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Hand over" }));
    expect(within(dialog).getByText("Choose who takes them over.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("combobox", { name: "Hand over to" }));
    await user.click(await screen.findByRole("option", { name: "Nirav Shah" }));
    await user.click(within(dialog).getByRole("checkbox", { name: /Then deactivate/ }));
    await user.click(within(dialog).getByRole("button", { name: "Hand over" }));
    expect(await within(dialog).findByText(/now belong to Nirav Shah/)).toHaveTextContent(
      "Kajal Solanki is deactivated",
    );
  });
});

describe("[ADMN-003] NewPerson", () => {
  beforeEach(reset);
  afterEach(reset);

  it("names what's missing, then adds a staff member and shows their password once", async () => {
    signInAs("admin");
    const user = show(<NewPerson />);
    await user.click(await screen.findByRole("button", { name: "Add the person" }));
    expect(screen.getByText("Enter their full name.")).toBeInTheDocument();
    expect(screen.getByText("Enter their work email.")).toBeInTheDocument();
    expect(screen.getByText("Choose their role.")).toBeInTheDocument();
    expect(screen.getByText("Choose their office.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Full name"), "Kiran Makwana");
    await user.type(screen.getByLabelText("Work email"), "kiran.makwana@polysil.in");
    await user.click(screen.getByRole("combobox", { name: "Role" }));
    await user.click(await screen.findByRole("option", { name: "Account Manager" }));
    await user.type(screen.getByRole("combobox", { name: "Office" }), "Head");
    await user.click(await screen.findByRole("option", { name: /Head Office/ }));
    const password = valueOf(screen.getByLabelText("Temporary password"));
    await user.click(screen.getByRole("button", { name: "Add the person" }));

    expect(
      await screen.findByRole("heading", { name: "Kiran Makwana is added" }),
    ).toBeInTheDocument();
    expect(screen.getByText(password)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open their page" })).toBeInTheDocument();
  });

  it("puts a refused field on its input", async () => {
    signInAs("admin");
    const user = show(<NewPerson />);
    await user.type(await screen.findByLabelText("Full name"), "Duplicate Asha");
    await user.type(screen.getByLabelText("Work email"), "asha@polysil.in");
    await user.click(screen.getByRole("combobox", { name: "Role" }));
    await user.click(await screen.findByRole("option", { name: "Marketing" }));
    await user.type(screen.getByRole("combobox", { name: "Office" }), "Head");
    await user.click(await screen.findByRole("option", { name: /Head Office/ }));
    await user.click(screen.getByRole("button", { name: "Add the person" }));
    expect(await screen.findByText("Already used by someone else.")).toBeInTheDocument();
    expect(screen.getByLabelText("Work email")).toHaveAttribute("aria-invalid", "true");
  });
});

describe("[ADMN-004] EditPerson", () => {
  beforeEach(reset);
  afterEach(reset);

  it("sends only what changed, then opens the person", async () => {
    signInAs("admin");
    const bodies: unknown[] = [];
    server.events.on("request:start", ({ request }) => {
      if (request.method === "PATCH")
        void request
          .clone()
          .json()
          .then((body: unknown) => bodies.push(body));
    });
    const id = idOf("Dilip Parmar");
    const user = show(<EditPerson userId={id} />);
    const name = await screen.findByLabelText("Full name");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    await user.clear(name);
    await user.type(name, "Dilip K. Parmar");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(`/users/${id}`);
    });
    expect(bodies).toEqual([{ full_name: "Dilip K. Parmar" }]);
    server.events.removeAllListeners();
  });
});
