import { afterEach, describe, expect, it } from "vitest";

import { isApiError } from "@/lib/api/errors";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockDb, resetMockDb } from "@/mocks/db";

import {
  listConversations,
  listMessages,
  markConversationRead,
  searchStaffDirectory,
  sendMessage,
  startConversation,
} from "./messages.api";

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

    expect(message.resource).toEqual({
      type: "lead",
      id: lead.id,
      label: `${lead.customerName} · ${lead.code}`,
    });
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

  it("starts a new, empty conversation with someone new", async () => {
    const conversation = await startConversation("usr-007");

    expect(conversation.participant.name).toBe("Imran Sheikh");
    expect(conversation.lastMessage).toBeNull();
    const list = await listConversations();
    expect(list.items.some((item) => item.id === conversation.id)).toBe(true);
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

    const result = await markConversationRead("conv-001");

    expect(result.unreadTotal).toBe(before.unreadTotal - unread);
  });
});
