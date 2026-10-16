import { describe, expect, it } from "vitest";

import type {
  Conversation,
  ConversationList,
  Message,
} from "@/features/messages/api/messages.schemas";

import { withConversationRead, withLastMessage } from "./conversation-cache";
import { continuesGroup, describePerson, formatDayLabel } from "./format-messages";
import { parseShareParam, toShareParam } from "./share-attachment";

function conversation(id: string, updatedAt: string, unreadCount: number): Conversation {
  return {
    id,
    participant: {
      id: `usr-${id}`,
      name: `Person ${id}`,
      roleName: null,
      orgUnitName: null,
      isActive: true,
    },
    lastMessage: null,
    unreadCount,
    updatedAt,
  };
}

const LIST: ConversationList = {
  items: [
    conversation("a", "2026-09-15T10:00:00.000Z", 2),
    conversation("b", "2026-09-15T09:00:00.000Z", 1),
  ],
  unreadTotal: 3,
};

describe("[MSG-003] share links", () => {
  it("reads a shared lead from the URL and ignores anything else", () => {
    expect(parseShareParam("lead:lead-10001")).toEqual({ type: "lead", id: "lead-10001" });
    expect(parseShareParam("sales_order:so-1")).toBeNull();
    expect(parseShareParam("lead:../../admin")).toBeNull();
    expect(parseShareParam(null)).toBeNull();
    expect(toShareParam({ type: "lead", id: "lead-10001" })).toBe("lead:lead-10001");
  });
});

describe("[MSG-002] thread formatting", () => {
  const now = new Date("2026-09-15T10:00:00+05:30");

  function message(id: string, senderId: string, createdAt: string): Message {
    return { id, conversationId: "a", senderId, body: "Hi", resource: null, createdAt };
  }

  it("labels days as Today, Yesterday or a date, in India time", () => {
    expect(formatDayLabel("2026-09-15T08:00:00+05:30", now)).toBe("Today");
    expect(formatDayLabel("2026-09-14T23:30:00+05:30", now)).toBe("Yesterday");
    expect(formatDayLabel("2026-09-10T12:00:00+05:30", now)).toMatch(/10 Sep/);
  });

  it("groups a sender's messages sent within five minutes", () => {
    const first = message("1", "usr-002", "2026-09-15T09:00:00+05:30");
    const soon = message("2", "usr-002", "2026-09-15T09:03:00+05:30");
    const later = message("3", "usr-002", "2026-09-15T09:20:00+05:30");
    const reply = message("4", "usr-001", "2026-09-15T09:21:00+05:30");

    expect(continuesGroup(first, soon)).toBe(true);
    expect(continuesGroup(soon, later)).toBe(false);
    expect(continuesGroup(later, reply)).toBe(false);
    expect(continuesGroup(undefined, first)).toBe(false);
  });

  it("describes a colleague by role and office, skipping what is missing", () => {
    expect(
      describePerson({
        id: "usr-002",
        name: "Priya Nair",
        roleName: "District Manager",
        orgUnitName: "Vadodara District",
        isActive: true,
      }),
    ).toBe("District Manager · Vadodara District");
    expect(
      describePerson({
        id: "x",
        name: "X",
        roleName: null,
        orgUnitName: "Head Office",
        isActive: true,
      }),
    ).toBe("Head Office");
  });
});

describe("[MSG-001] conversation list updates", () => {
  it("moves a conversation to the top when a message is sent in it", () => {
    const message: Message = {
      id: "msg-1",
      conversationId: "b",
      senderId: "usr-001",
      body: "Hello",
      resource: null,
      createdAt: "2026-09-15T11:00:00.000Z",
    };

    const next = withLastMessage(LIST, message);

    expect(next.items.map((item) => item.id)).toEqual(["b", "a"]);
    expect(next.items[0]?.lastMessage).toEqual(message);
  });

  it("clears a conversation's unread count and takes the server's total", () => {
    const next = withConversationRead(LIST, "a", 1);

    expect(next.items.map((item) => item.unreadCount)).toEqual([0, 1]);
    expect(next.unreadTotal).toBe(1);
  });
});
