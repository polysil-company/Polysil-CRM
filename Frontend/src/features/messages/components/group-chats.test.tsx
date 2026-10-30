import type { QueryClient } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { sessionKeys } from "@/features/session/api/session.queries";
import { meResponseSchema } from "@/features/session/api/session.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { createTestQueryClient, renderWithProviders } from "@/test/render";

import { ConversationList } from "./conversation-list";
import { ConversationThread } from "./conversation-thread";

const push = vi.fn();
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
  useRouter: () => ({ push, replace }),
}));

function signedInClient(): QueryClient {
  const queryClient = createTestQueryClient();
  queryClient.setQueryData(
    sessionKeys.current(),
    meResponseSchema.parse(mockMeFor("state_manager")),
  );
  return queryClient;
}

function show(ui: React.JSX.Element): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      {ui}
      <Toaster />
    </>,
    { queryClient: signedInClient() },
  );
  return user;
}

function reset(): void {
  resetMockDb();
  push.mockReset();
  replace.mockReset();
}

describe("[MSG-006] Group chats in the conversation list", () => {
  afterEach(reset);

  it("lists a group by its name and size, even before anyone writes", async () => {
    show(<ConversationList activeConversationId={null} />);

    const nav = await screen.findByRole("navigation", { name: "Conversations" });
    expect(within(nav).getByRole("link", { name: /Saurashtra sales/ })).toHaveTextContent(
      "4 members · Dispatch says the drip kits arrive Friday.",
    );
    expect(within(nav).getByRole("link", { name: /Dispatch coordination/ })).toHaveTextContent(
      "3 members · No messages yet",
    );
  });

  it("makes a group from a name and chosen colleagues, and opens it", async () => {
    const user = show(<ConversationList activeConversationId={null} />);
    await user.click(await screen.findByRole("button", { name: "New group" }));
    const dialog = await screen.findByRole("dialog", { name: "New group" });

    await user.click(within(dialog).getByRole("button", { name: "Make the group" }));
    expect(within(dialog).getByText("Name the group.")).toBeInTheDocument();
    expect(within(dialog).getByText("Choose at least one colleague.")).toBeInTheDocument();

    await user.type(within(dialog).getByRole("textbox", { name: "Group name" }), "Kutch push");
    await user.click(await within(dialog).findByRole("checkbox", { name: /Kavita Joshi/ }));
    await user.click(within(dialog).getByRole("checkbox", { name: /Anjali Verma/ }));
    expect(within(dialog).getByText("2 chosen: Kavita Joshi, Anjali Verma")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Make the group" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(expect.stringMatching(/^\/messages\/grp-/));
    });
    const made = mockDb.conversations.find((item) => item.group?.name === "Kutch push");
    expect(made?.kind).toBe("group");
    expect((mockDb.groupMembers.get(made?.id ?? "") ?? []).map((member) => member.userId)).toEqual([
      "usr-001",
      "usr-004",
      "usr-008",
    ]);
  });
});

describe("[MSG-006] A group thread", () => {
  afterEach(reset);

  it("names each sender, and the group with its size", async () => {
    show(<ConversationThread conversationId="grp-001" />);

    expect(await screen.findByRole("heading", { name: "Saurashtra sales" })).toBeInTheDocument();
    expect(screen.getByText("4 members")).toBeInTheDocument();
    const log = screen.getByRole("log", { name: "Messages" });
    expect(await within(log).findByText("Priya Nair")).toBeInTheDocument();
    expect(within(log).getByText("Rohan Mehta")).toBeInTheDocument();
    expect(within(log).getByText("Sanjay Rao")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message Saurashtra sales" })).toBeInTheDocument();
  });

  it("shows the manager members, rename and remove in Group info", async () => {
    const user = show(<ConversationThread conversationId="grp-001" />);
    await user.click(await screen.findByRole("button", { name: "Group info" }));
    const dialog = await screen.findByRole("dialog", { name: "Group info" });

    expect(await within(dialog).findByText("(you)")).toBeInTheDocument();
    expect(within(dialog).getByText("Manages this group")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Remove Rohan Mehta" }));
    expect(await screen.findByText("Rohan Mehta removed")).toBeInTheDocument();
    expect(await within(dialog).findByText("Left the group")).toBeInTheDocument();

    const name = within(dialog).getByRole("textbox", { name: "Group name" });
    await user.clear(name);
    await user.type(name, "Saurashtra sales team");
    await user.click(within(dialog).getByRole("button", { name: "Rename" }));
    expect(await screen.findByText("Group renamed")).toBeInTheDocument();
    expect(mockDb.conversations.find((item) => item.id === "grp-001")?.group?.name).toBe(
      "Saurashtra sales team",
    );
  });

  it("adds people to a group the user doesn't manage, and leaves it", async () => {
    const user = show(<ConversationThread conversationId="grp-002" />);
    await user.click(await screen.findByRole("button", { name: "Group info" }));
    const dialog = await screen.findByRole("dialog", { name: "Group info" });
    await within(dialog).findByText("(you)");

    // Only the manager renames and removes.
    expect(within(dialog).queryByRole("textbox", { name: "Group name" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /^Remove / })).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Add people" }));
    await user.click(await within(dialog).findByRole("checkbox", { name: /Imran Sheikh/ }));
    // Someone already in is not offered.
    expect(
      within(dialog).queryByRole("checkbox", { name: /Neha Kulkarni/ }),
    ).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Add 1" }));
    expect(await screen.findByText("1 colleague added")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Leave the group" }));
    await user.click(within(dialog).getByRole("button", { name: "Leave" }));
    expect(await screen.findByText("You left the group")).toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith("/messages");
  });

  it("leaves the screen when the user is no longer in the group", async () => {
    show(<ConversationThread conversationId="grp-001" />);
    expect(await screen.findByRole("heading", { name: "Saurashtra sales" })).toBeInTheDocument();

    server.use(
      http.get(buildApiUrl("/conversations/:conversationId/messages"), () =>
        HttpResponse.json({ error: { code: "not_found", message: "Gone" } }, { status: 404 }),
      ),
    );
    // The next poll answers 404: the manager removed the user.
    await waitFor(
      () => {
        expect(replace).toHaveBeenCalledWith("/messages");
      },
      { timeout: 15_000 },
    );
    expect(await screen.findByText("You're no longer in this group")).toBeInTheDocument();
  }, 20_000);
});
