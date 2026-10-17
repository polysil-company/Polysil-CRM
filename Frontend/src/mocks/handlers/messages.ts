import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  addMembersRequestSchema,
  createGroupRequestSchema,
  GROUP_MAX_MEMBERS,
  renameGroupRequestSchema,
  sendMessageRequestSchema,
  startConversationRequestSchema,
  type ConversationListResponse,
  type ConversationResponse,
  type ConversationWire,
  type MarkConversationReadResponse,
  type MemberListResponse,
  type MessageListResponse,
  type MessageResponse,
  type MessageWire,
  type PersonWire,
  type StaffDirectoryResponse,
} from "@/features/messages/api/messages.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import {
  findMockStaff,
  MOCK_CURRENT_STAFF_ID,
  MOCK_CURRENT_STAFF_PERSON,
  MOCK_STAFF_DIRECTORY,
  mockLeadLabel,
  type MockGroupMember,
} from "@/mocks/data/messages";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/** The mark-read body: `up_to`, the newest message the screen shows, or nothing. */
const markReadRequestSchema = z.object({ up_to: z.string().min(1).optional() });

/** Mock-only behaviour. vitest.setup.ts turns the automatic reply off. */
export const mockMessagingOptions: { autoReplyMs: number | null } = { autoReplyMs: 6000 };

const AUTO_REPLIES = [
  "Got it, thanks.",
  "Sounds good — I'll update the lead.",
  "Noted. I'll confirm by this evening.",
  "Okay, sharing the details shortly.",
];

let sequence = 0;

function nextId(prefix: string): string {
  sequence += 1;
  return `${prefix}-${String(Date.now())}-${String(sequence)}`;
}

function positiveInt(raw: string | null, fallback: number): number {
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

/** The backend's refusal for every dealer, distributor and sub-dealer. */
function forbidden(): Response {
  return errorResponse(403, "insufficient_permission", "Messages are for Polysil staff.");
}

function conversationNotFound(): Response {
  return errorResponse(404, "not_found", "No such conversation.");
}

function validation(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

/** Their messages after `upTo`; every one of theirs when `upTo` is null. */
function unreadAfter(conversation: ConversationWire, upTo: string | null): number {
  const thread = mockDb.messages
    .filter((message) => message.conversation_id === conversation.id)
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
  const from = upTo === null ? thread.length : thread.findIndex((message) => message.id === upTo);
  return thread.slice(from + 1).filter((message) => message.sender_id !== MOCK_CURRENT_STAFF_ID)
    .length;
}

// ── MSG-006 · groups ──────────────────────────────────────────────────────────

function membersOf(conversationId: string): MockGroupMember[] {
  return mockDb.groupMembers.get(conversationId) ?? [];
}

function currentMembersOf(conversationId: string): MockGroupMember[] {
  return membersOf(conversationId).filter((member) => member.leftAt === null);
}

function inGroup(conversationId: string, userId: string): boolean {
  return currentMembersOf(conversationId).some((member) => member.userId === userId);
}

function personOf(userId: string): PersonWire {
  return userId === MOCK_CURRENT_STAFF_ID
    ? MOCK_CURRENT_STAFF_PERSON
    : (findMockStaff(userId) ?? { id: userId, full_name: "Former colleague", is_active: false });
}

/** A group's name, size and manager, as they stand now. */
function withGroupInfo(conversation: ConversationWire): ConversationWire {
  if (conversation.kind !== "group" || !conversation.group) return conversation;
  const current = currentMembersOf(conversation.id);
  const managerId = current.find((member) => member.isManager)?.userId ?? null;
  return {
    ...conversation,
    group: {
      ...conversation.group,
      member_count: current.length,
      manager_id: managerId,
      i_manage: managerId === MOCK_CURRENT_STAFF_ID,
    },
  };
}

/** Someone who leaves sees nothing of the group: it isn't theirs while they are out. */
function isMine(conversation: ConversationWire): boolean {
  return conversation.kind !== "group" || inGroup(conversation.id, MOCK_CURRENT_STAFF_ID);
}

function findConversation(conversationId: string): ConversationWire | undefined {
  const conversation = mockDb.conversations.find((item) => item.id === conversationId);
  return conversation !== undefined && isMine(conversation)
    ? withGroupInfo(conversation)
    : undefined;
}

function findGroup(conversationId: string): ConversationWire | undefined {
  const conversation = findConversation(conversationId);
  return conversation?.kind === "group" ? conversation : undefined;
}

function memberList(conversationId: string): MemberListResponse {
  // Current members first, then those who have left; each by when they were added.
  const members = [...membersOf(conversationId)].sort(
    (a, b) =>
      Number(a.leftAt !== null) - Number(b.leftAt !== null) ||
      Date.parse(a.addedAt) - Date.parse(b.addedAt),
  );
  return {
    data: members.map((member) => ({
      person: personOf(member.userId),
      added_at: member.addedAt,
      left_at: member.leftAt,
      is_manager: member.isManager,
    })),
  };
}

/** Colleagues who may join a group: active staff in the directory, not the user. */
function joinable(userIds: readonly string[]): boolean {
  return userIds.every((id) => {
    const person = findMockStaff(id);
    return person !== undefined && person.is_active !== false;
  });
}

function unreadTotal(): number {
  return mockDb.conversations.reduce((sum, conversation) => sum + conversation.unread_count, 0);
}

function appendMessage(message: MessageWire, unreadIncrement: number): void {
  mockDb.messages = [...mockDb.messages, message];
  mockDb.conversations = mockDb.conversations.map((conversation) =>
    conversation.id === message.conversation_id
      ? {
          ...conversation,
          last_message: message,
          updated_at: message.created_at,
          unread_count: conversation.unread_count + unreadIncrement,
        }
      : conversation,
  );
}

/** The colleague "replies" a few seconds later, so polling can be seen working in the browser. */
function scheduleReply(conversation: ConversationWire): void {
  const { autoReplyMs } = mockMessagingOptions;
  if (autoReplyMs === null) {
    return;
  }
  const body = AUTO_REPLIES[sequence % AUTO_REPLIES.length] ?? "Okay.";
  // In a group, the first other member answers.
  const replierId =
    conversation.participant?.id ??
    currentMembersOf(conversation.id).find((member) => member.userId !== MOCK_CURRENT_STAFF_ID)
      ?.userId;
  if (replierId === undefined) {
    return;
  }
  setTimeout(() => {
    if (findConversation(conversation.id) === undefined) {
      return;
    }
    appendMessage(
      {
        id: nextId("msg"),
        conversation_id: conversation.id,
        sender_id: replierId,
        body,
        resource: null,
        created_at: new Date().toISOString(),
      },
      1,
    );
  }, autoReplyMs);
}

export const messageHandlers = [
  http.get(buildApiUrl("/conversations"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    if (scenario === "contract") {
      // Deliberately wrong shape: exercises CONTRACT_VIOLATION handling end to end.
      return HttpResponse.json({ data: [{ id: 1, participant: null }], meta: null });
    }

    // A conversation opened but never written in is not listed, as on the backend.
    const conversations =
      scenario === "empty"
        ? []
        : mockDb.conversations
            // A group is listed from the moment it is made, while the user is in it.
            .filter((conversation) =>
              conversation.kind === "group"
                ? isMine(conversation)
                : conversation.last_message !== null,
            )
            .map(withGroupInfo)
            .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
    const body: ConversationListResponse = {
      data: conversations,
      meta: { unread_total: scenario === "empty" ? 0 : unreadTotal() },
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/staff-directory"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const url = new URL(request.url);
    const query = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const limit = Math.min(100, positiveInt(url.searchParams.get("limit"), 50));
    // Every active colleague: someone who has left is not offered.
    const people =
      scenario === "empty"
        ? []
        : MOCK_STAFF_DIRECTORY.filter(
            (person) =>
              person.is_active !== false &&
              [person.full_name, person.role_name ?? "", person.org_unit_name ?? ""].some((field) =>
                field.toLowerCase().includes(query),
              ),
          );

    const body: StaffDirectoryResponse = { data: people.slice(0, limit) };
    return HttpResponse.json(body);
  }),

  http.post(buildApiUrl("/conversations"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const payload: unknown = await request.json();
    const parsed = startConversationRequestSchema.safeParse(payload);
    const participant = parsed.success ? findMockStaff(parsed.data.participant_id) : undefined;
    if (
      participant === undefined ||
      participant.id === MOCK_CURRENT_STAFF_ID ||
      participant.is_active === false
    ) {
      return validation({ participant_id: "not someone you can message" });
    }

    const existing = mockDb.conversations.find(
      (conversation) =>
        conversation.kind !== "group" && conversation.participant?.id === participant.id,
    );
    if (existing) {
      const body: ConversationResponse = { data: existing };
      return HttpResponse.json(body);
    }

    const conversation: ConversationWire = {
      id: nextId("conv"),
      kind: "direct",
      participant,
      last_message: null,
      unread_count: 0,
      updated_at: new Date().toISOString(),
    };
    mockDb.conversations = [conversation, ...mockDb.conversations];
    const body: ConversationResponse = { data: conversation };
    return HttpResponse.json(body, { status: 201 });
  }),

  // BE-021: one conversation, written in or not; 404 when it is not the caller's.
  http.get(buildApiUrl("/conversations/:conversationId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const conversation = findConversation(String(params.conversationId));
    if (conversation === undefined) return conversationNotFound();
    const body: ConversationResponse = { data: conversation };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/conversations/:conversationId/messages"), async ({ params, request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const conversationId = String(params.conversationId);
    if (findConversation(conversationId) === undefined) {
      return conversationNotFound();
    }

    const limit = Math.min(100, positiveInt(new URL(request.url).searchParams.get("limit"), 50));
    const thread =
      scenario === "empty"
        ? []
        : mockDb.messages
            .filter((message) => message.conversation_id === conversationId)
            .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));

    const body: MessageListResponse = {
      data: thread.slice(-limit),
      meta: { next_cursor: null },
    };
    return HttpResponse.json(body);
  }),

  http.post(buildApiUrl("/conversations/:conversationId/messages"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const conversation = findConversation(String(params.conversationId));
    if (conversation === undefined) {
      return conversationNotFound();
    }

    // Never in a group: a member who leaves the company stays listed.
    if (conversation.kind !== "group" && conversation.participant?.is_active === false) {
      return errorResponse(422, "participant_inactive", "That colleague has left.", {
        participant: "no longer active",
      });
    }

    const payload: unknown = await request.json();
    const parsed = sendMessageRequestSchema.safeParse(payload);
    if (!parsed.success) {
      return validation({ body: "a message of 1 to 2,000 characters" });
    }

    // A lead the sender cannot see is never linked.
    const { resource } = parsed.data;
    const lead =
      resource?.type === "lead" ? mockDb.leads.find((item) => item.id === resource.id) : undefined;
    if (resource !== null && lead === undefined) {
      return validation({ resource: "not a lead you can see" });
    }

    const message: MessageWire = {
      id: nextId("msg"),
      conversation_id: conversation.id,
      sender_id: MOCK_CURRENT_STAFF_ID,
      body: parsed.data.body,
      resource: lead ? { type: "lead", id: lead.id, label: mockLeadLabel(lead) } : null,
      created_at: new Date().toISOString(),
    };
    appendMessage(message, 0);
    scheduleReply(conversation);

    const body: MessageResponse = { data: message };
    return HttpResponse.json(body, { status: 201 });
  }),

  http.post(buildApiUrl("/conversations/:conversationId/read"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const conversation = findConversation(String(params.conversationId));
    if (conversation === undefined) {
      return conversationNotFound();
    }

    // Read up to the newest message the screen shows; left out, everything so far.
    const payload: unknown = await request.json().catch(() => ({}));
    const upTo = markReadRequestSchema.safeParse(payload).data?.up_to ?? null;
    if (
      upTo !== null &&
      !mockDb.messages.some(
        (message) => message.id === upTo && message.conversation_id === conversation.id,
      )
    ) {
      return validation({ up_to: "not a message of this conversation" });
    }

    const unread = unreadAfter(conversation, upTo);
    mockDb.conversations = mockDb.conversations.map((item) =>
      // A mark never moves backwards: it only ever lowers the count.
      item.id === conversation.id
        ? { ...item, unread_count: Math.min(item.unread_count, unread) }
        : item,
    );
    const body: MarkConversationReadResponse = { data: { unread_total: unreadTotal() } };
    return HttpResponse.json(body);
  }),

  http.post(buildApiUrl("/conversations/groups"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const parsed = createGroupRequestSchema.safeParse(await request.json());
    if (!parsed.success) {
      return validation({ name: "a name of 1 to 80", member_ids: "1 to 49 colleagues" });
    }
    const memberIds = [...new Set(parsed.data.member_ids)].filter(
      (id) => id !== MOCK_CURRENT_STAFF_ID,
    );
    if (memberIds.length === 0 || !joinable(memberIds)) {
      return validation({ member_ids: "not everyone chosen is active staff" });
    }

    const now = new Date().toISOString();
    const id = nextId("grp");
    mockDb.groupMembers.set(id, [
      { userId: MOCK_CURRENT_STAFF_ID, addedAt: now, leftAt: null, isManager: true },
      ...memberIds.map((userId) => ({ userId, addedAt: now, leftAt: null, isManager: false })),
    ]);
    const conversation: ConversationWire = {
      id,
      kind: "group",
      participant: null,
      group: {
        name: parsed.data.name,
        member_count: memberIds.length + 1,
        manager_id: MOCK_CURRENT_STAFF_ID,
        i_manage: true,
      },
      last_message: null,
      unread_count: 0,
      updated_at: now,
    };
    mockDb.conversations = [conversation, ...mockDb.conversations];
    const body: ConversationResponse = { data: conversation };
    return HttpResponse.json(body, { status: 201 });
  }),

  http.patch(buildApiUrl("/conversations/:conversationId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const conversation = findConversation(String(params.conversationId));
    if (conversation === undefined) return conversationNotFound();
    if (conversation.kind !== "group" || !conversation.group) {
      return errorResponse(422, "not_a_group", "Only a group has a name.");
    }
    if (!conversation.group.i_manage) {
      return errorResponse(403, "insufficient_permission", "Only the group's manager renames it.");
    }
    const parsed = renameGroupRequestSchema.safeParse(await request.json());
    if (!parsed.success) return validation({ name: "a name of 1 to 80" });

    const { name } = parsed.data;
    mockDb.conversations = mockDb.conversations.map((item) =>
      item.id === conversation.id && item.group
        ? { ...item, group: { ...item.group, name } }
        : item,
    );
    const renamed = findConversation(conversation.id);
    if (renamed === undefined) return conversationNotFound();
    const body: ConversationResponse = { data: renamed };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/conversations/:conversationId/members"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const group = findGroup(String(params.conversationId));
    if (group === undefined) return conversationNotFound();
    return HttpResponse.json(memberList(group.id));
  }),

  http.post(buildApiUrl("/conversations/:conversationId/members"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const group = findGroup(String(params.conversationId));
    if (group === undefined) return conversationNotFound();
    const parsed = addMembersRequestSchema.safeParse(await request.json());
    if (!parsed.success || !joinable(parsed.data.user_ids)) {
      return validation({ user_ids: "not everyone chosen is active staff" });
    }

    const members = membersOf(group.id);
    const joining = [...new Set(parsed.data.user_ids)].filter((id) => !inGroup(group.id, id));
    if (currentMembersOf(group.id).length + joining.length > GROUP_MAX_MEMBERS) {
      return errorResponse(422, "group_full", "A group takes 50 people.", {
        user_ids: "the group would be over 50",
      });
    }
    const now = new Date().toISOString();
    for (const userId of joining) {
      const before = members.find((member) => member.userId === userId);
      if (before === undefined) {
        members.push({ userId, addedAt: now, leftAt: null, isManager: false });
      } else {
        // Back again: they see the whole history.
        before.leftAt = null;
        before.addedAt = now;
      }
    }
    mockDb.groupMembers.set(group.id, members);
    return HttpResponse.json(memberList(group.id));
  }),

  http.delete(buildApiUrl("/conversations/:conversationId/members/:userId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const group = findGroup(String(params.conversationId));
    const userId = String(params.userId);
    if (group === undefined || !inGroup(group.id, userId)) return conversationNotFound();
    const leaving = userId === MOCK_CURRENT_STAFF_ID;
    if (!leaving && group.group?.i_manage !== true) {
      return errorResponse(
        403,
        "insufficient_permission",
        "Only the group's manager removes people.",
      );
    }

    const members = membersOf(group.id);
    const member = members.find((item) => item.userId === userId && item.leftAt === null);
    if (member === undefined) return conversationNotFound();
    member.leftAt = new Date().toISOString();
    if (member.isManager) {
      // The longest-standing active member takes over.
      member.isManager = false;
      const next = members
        .filter((item) => item.leftAt === null)
        .sort((a, b) => Date.parse(a.addedAt) - Date.parse(b.addedAt))[0];
      if (next !== undefined) next.isManager = true;
    }
    return new HttpResponse(null, { status: 204 });
  }),
];
