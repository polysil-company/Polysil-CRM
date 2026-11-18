import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";

import {
  addMembers,
  createGroup,
  getConversation,
  listConversations,
  listMembers,
  listMessages,
  markConversationRead,
  removeMember,
  renameGroup,
  searchStaffDirectory,
  sendMessage,
  startConversation,
} from "./messages.api";

async function failureOf(request: Promise<unknown>): Promise<unknown> {
  try {
    await request;
  } catch (error) {
    return error;
  }
  throw new Error("Expected the request to fail");
}

async function statusOfFailure(request: Promise<unknown>): Promise<number | undefined> {
  try {
    await request;
  } catch (error) {
    return isApiError(error) ? error.status : undefined;
  }
  throw new Error("Expected the request to fail");
}

describe("[MSG-001] listConversations", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("lists the most recent conversation first, with the unread total", async () => {
    const list = await listConversations();

    expect(list.items.length).toBeGreaterThan(0);
    const updated = list.items.map((conversation) => Date.parse(conversation.updatedAt));
    expect(updated).toEqual([...updated].sort((a, b) => b - a));
    expect(list.unreadTotal).toBe(
      list.items.reduce((sum, conversation) => sum + conversation.unreadCount, 0),
    );
  });

  it("refuses partner users", async () => {
    writeMockRole("dealer");

    expect(await statusOfFailure(listConversations())).toBe(403);
  });
});

describe("[MSG-002] listMessages", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("returns the thread oldest first, with linked leads", async () => {
    const page = await listMessages("conv-001");

    const created = page.items.map((message) => Date.parse(message.createdAt));
    expect(created).toEqual([...created].sort((a, b) => a - b));
    expect(page.items.some((message) => message.resource?.type === "lead")).toBe(true);
  });

  it("fails with 404 for a conversation that does not exist", async () => {
    expect(await statusOfFailure(listMessages("conv-missing"))).toBe(404);
  });
});

describe("[MSG-003] sendMessage", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("adds the message and moves its conversation to the top", async () => {
    const message = await sendMessage("conv-003", { body: "  See you at 10.  ", resource: null });

    expect(message.body).toBe("See you at 10.");
    const list = await listConversations();
    expect(list.items[0]?.id).toBe("conv-003");
    expect(list.items[0]?.lastMessage?.id).toBe(message.id);
  });

  it("links a lead and names it", async () => {
    const lead = mockDb.leads[0];
    if (lead === undefined) {
      throw new Error("Mock database has no leads");
    }

    const message = await sendMessage("conv-003", {
      body: "Please call them today.",
      resource: { type: "lead", id: lead.id },
    });

    // The backend labels a linked lead with its inquiry number.
    expect(message.resource).toEqual({ type: "lead", id: lead.id, label: lead.inquiry_no });
  });

  it("refuses a lead the sender cannot see, on `resource`", async () => {
    const error = await failureOf(
      sendMessage("conv-003", { body: "Look", resource: { type: "lead", id: "lead-unseen" } }),
    );

    expect(error).toMatchObject({ status: 422, code: "validation_error" });
    expect(readFieldErrors(error)).toEqual({ resource: "not a lead you can see" });
  });

  it("refuses a message to a colleague who has left", async () => {
    const error = await failureOf(sendMessage("conv-005", { body: "Hello?", resource: null }));

    expect(error).toMatchObject({ status: 422, code: "participant_inactive" });
  });

  it("rejects an empty message", async () => {
    expect(await statusOfFailure(sendMessage("conv-003", { body: "   ", resource: null }))).toBe(
      422,
    );
  });
});

describe("[MSG-004] staff directory and new conversations", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("finds colleagues by role", async () => {
    const people = await searchStaffDirectory("dispatch");

    expect(people.map((person) => person.name)).toEqual(["Neha Kulkarni"]);
  });

  it("reuses the conversation that already exists with a colleague", async () => {
    const conversation = await startConversation("usr-002");

    expect(conversation.id).toBe("conv-001");
  });

  it("starts a new conversation, listed only once someone writes in it", async () => {
    const conversation = await startConversation("usr-007");

    expect(conversation.participant?.name).toBe("Imran Sheikh");
    expect(conversation.lastMessage).toBeNull();
    expect((await listConversations()).items.some((item) => item.id === conversation.id)).toBe(
      false,
    );

    await sendMessage(conversation.id, { body: "Hello Imran", resource: null });
    expect((await listConversations()).items[0]?.id).toBe(conversation.id);
  });

  it("reads one conversation on its own, before anyone writes in it (BE-021)", async () => {
    const started = await startConversation("usr-007");

    const conversation = await getConversation(started.id);

    expect(conversation).toMatchObject({
      id: started.id,
      participant: { name: "Imran Sheikh" },
      lastMessage: null,
      unreadCount: 0,
    });
    expect((await getConversation("conv-001")).participant?.id).toBe("usr-002");
  });

  it("fails with 404 for a conversation that is not the user's", async () => {
    expect(await statusOfFailure(getConversation("conv-missing"))).toBe(404);
  });

  it("offers only colleagues still at Polysil, and refuses one who has left", async () => {
    const people = await searchStaffDirectory("");

    expect(people.every((person) => person.isActive)).toBe(true);
    expect(people.some((person) => person.name === "Meera Iyer")).toBe(false);
    expect(await statusOfFailure(startConversation("usr-010"))).toBe(422);
  });

  it("keeps a colleague who has left readable in their old conversation", async () => {
    const list = await listConversations();

    expect(list.items.find((item) => item.id === "conv-005")?.participant).toMatchObject({
      name: "Meera Iyer",
      isActive: false,
    });
  });
});

describe("[MSG-005] markConversationRead", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("clears the conversation's unread messages from the total", async () => {
    const before = await listConversations();
    const unread = before.items.find((item) => item.id === "conv-001")?.unreadCount ?? 0;
    expect(unread).toBeGreaterThan(0);

    const result = await markConversationRead("conv-001", null);

    expect(result.unreadTotal).toBe(before.unreadTotal - unread);
  });

  it("reads up to the message on screen, so a later one stays unread", async () => {
    const page = await listMessages("conv-001");
    // Their two unread messages are the last two: the screen shows up to the first of them.
    const shown = page.items.at(-2)?.id ?? "";
    let sent: unknown;
    server.use(
      // Notes the body, then falls through to the mock backend's own handler.
      http.post(buildApiUrl("/conversations/:conversationId/read"), async ({ request }) => {
        sent = await request.clone().json();
      }),
    );

    await markConversationRead("conv-001", shown);

    expect(sent).toEqual({ up_to: shown });
    const after = await listConversations();
    expect(after.items.find((item) => item.id === "conv-001")?.unreadCount).toBe(1);
  });

  it("refuses an `up_to` from another conversation", async () => {
    const other = (await listMessages("conv-003")).items[0]?.id ?? "";

    expect(await statusOfFailure(markConversationRead("conv-001", other))).toBe(422);
  });
});

describe("[MSG-006] group chats", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("lists a group from the moment it is made, by name and size, with no participant", async () => {
    const group = await createGroup({ name: "Kutch push", member_ids: ["usr-004", "usr-008"] });

    expect(group).toMatchObject({
      kind: "group",
      participant: null,
      lastMessage: null,
      group: { name: "Kutch push", memberCount: 3, iManage: true },
    });
    const listed = (await listConversations()).items.find((item) => item.id === group.id);
    expect(listed?.kind).toBe("group");
  });

  it("refuses a group with no one else in it", async () => {
    expect(await statusOfFailure(createGroup({ name: "Just me", member_ids: [] }))).toBe(422);
  });

  it("lists current members first, and takes someone back who had left", async () => {
    const members = await listMembers("grp-001");
    expect(members.map((member) => member.person.name)).toEqual([
      "Aarav Desai",
      "Priya Nair",
      "Rohan Mehta",
      "Sanjay Rao",
    ]);
    expect(members.find((member) => member.isManager)?.person.id).toBe("usr-001");

    await removeMember("grp-001", "usr-003");
    const after = await listMembers("grp-001");
    expect(after.at(-1)).toMatchObject({ person: { id: "usr-003" } });
    expect(after.at(-1)?.leftAt).not.toBeNull();

    const back = await addMembers("grp-001", { user_ids: ["usr-003"] });
    expect(back.filter((member) => member.leftAt === null)).toHaveLength(4);
  });

  it("refuses past 50 members, adding nobody", async () => {
    const members = mockDb.groupMembers.get("grp-001") ?? [];
    const filler = Array.from({ length: 46 }, (_, index) => ({
      userId: `usr-${String(index + 100)}`,
      addedAt: "2026-10-01T10:00:00+05:30",
      leftAt: null,
      isManager: false,
    }));
    mockDb.groupMembers.set("grp-001", [...members, ...filler]);

    const error = await failureOf(addMembers("grp-001", { user_ids: ["usr-004"] }));
    expect(isApiError(error) && error.code).toBe("group_full");
    expect(mockDb.groupMembers.get("grp-001")?.some((member) => member.userId === "usr-004")).toBe(
      false,
    );
  });

  it("lets only the manager rename or remove; a one-to-one conversation has no name", async () => {
    const renamed = await renameGroup("grp-001", { name: "Saurashtra sales team" });
    expect(renamed.kind === "group" && renamed.group.name).toBe("Saurashtra sales team");

    expect(await statusOfFailure(renameGroup("grp-002", { name: "Mine now" }))).toBe(403);
    expect(await statusOfFailure(removeMember("grp-002", "usr-006"))).toBe(403);
    const notAGroup = await failureOf(renameGroup("conv-001", { name: "Pair" }));
    expect(isApiError(notAGroup) && notAGroup.code).toBe("not_a_group");
  });

  it("drops a group the user leaves, and hands the group to the longest-standing member", async () => {
    await removeMember("grp-001", "usr-001");

    expect((await listConversations()).items.some((item) => item.id === "grp-001")).toBe(false);
    expect(await statusOfFailure(listMessages("grp-001"))).toBe(404);
    expect(mockDb.groupMembers.get("grp-001")?.find((member) => member.isManager)?.userId).toBe(
      "usr-002",
    );
  });

  it("reads an older answer without `kind` as one to one, and refuses a group without its group", async () => {
    server.use(
      http.get(buildApiUrl("/conversations/:conversationId"), ({ params }) =>
        HttpResponse.json({
          data: {
            id: String(params.conversationId),
            participant: { id: "usr-002", full_name: "Priya Nair" },
            last_message: null,
            unread_count: 0,
            updated_at: "2026-10-14T10:00:00+05:30",
          },
        }),
      ),
    );
    expect((await getConversation("conv-001")).kind).toBe("direct");

    server.use(
      http.get(buildApiUrl("/conversations/:conversationId"), ({ params }) =>
        HttpResponse.json({
          data: {
            id: String(params.conversationId),
            kind: "group",
            participant: null,
            last_message: null,
            unread_count: 0,
            updated_at: "2026-10-14T10:00:00+05:30",
          },
        }),
      ),
    );
    const error = await failureOf(getConversation("grp-001"));
    expect(isApiError(error) && error.kind).toBe("contract");
  });
});
