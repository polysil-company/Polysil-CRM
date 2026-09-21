import { http, HttpResponse } from "msw";

import {
  sendMessageRequestSchema,
  startConversationRequestSchema,
  type ConversationListResponse,
  type ConversationResponse,
  type ConversationWire,
  type MarkConversationReadResponse,
  type MessageListResponse,
  type MessageResponse,
  type MessageWire,
  type StaffDirectoryResponse,
} from "@/features/messages/api/messages.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import {
  findMockStaff,
  MOCK_CURRENT_STAFF_ID,
  MOCK_STAFF_DIRECTORY,
  mockLeadLabel,
} from "@/mocks/data/messages";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";

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

function forbidden(): Response {
  return HttpResponse.json(
    { error: { code: "FORBIDDEN", message: "Messages are available to Polysil staff only." } },
    { status: 403 },
  );
}

function conversationNotFound(conversationId: string): Response {
  return HttpResponse.json(
    {
      error: {
        code: "CONVERSATION_NOT_FOUND",
        message: `No conversation with id ${conversationId}`,
      },
    },
    { status: 404 },
  );
}

function findConversation(conversationId: string): ConversationWire | undefined {
  return mockDb.conversations.find((conversation) => conversation.id === conversationId);
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
  setTimeout(() => {
    if (findConversation(conversation.id) === undefined) {
      return;
    }
    appendMessage(
      {
        id: nextId("msg"),
        conversation_id: conversation.id,
        sender_id: conversation.participant.id,
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

    const conversations =
      scenario === "empty"
        ? []
        : [...mockDb.conversations].sort(
            (a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at),
          );
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
    const limit = Math.min(50, positiveInt(url.searchParams.get("limit"), 20));
    const people =
      scenario === "empty"
        ? []
        : MOCK_STAFF_DIRECTORY.filter((person) =>
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
    if (participant === undefined || participant.id === MOCK_CURRENT_STAFF_ID) {
      return HttpResponse.json(
        {
          error: {
            code: "PARTICIPANT_NOT_FOUND",
            message: "Choose a colleague from the directory.",
          },
        },
        { status: 422 },
      );
    }

    const existing = mockDb.conversations.find(
      (conversation) => conversation.participant.id === participant.id,
    );
    if (existing) {
      const body: ConversationResponse = { data: existing };
      return HttpResponse.json(body);
    }

    const conversation: ConversationWire = {
      id: nextId("conv"),
      participant,
      last_message: null,
      unread_count: 0,
      updated_at: new Date().toISOString(),
    };
    mockDb.conversations = [conversation, ...mockDb.conversations];
    const body: ConversationResponse = { data: conversation };
    return HttpResponse.json(body, { status: 201 });
  }),

  http.get(buildApiUrl("/conversations/:conversationId/messages"), async ({ params, request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const conversationId = String(params.conversationId);
    if (findConversation(conversationId) === undefined) {
      return conversationNotFound(conversationId);
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
      return conversationNotFound(String(params.conversationId));
    }

    const payload: unknown = await request.json();
    const parsed = sendMessageRequestSchema.safeParse(payload);
    if (!parsed.success) {
      return HttpResponse.json(
        {
          error: {
            code: "VALIDATION_FAILED",
            message: "The message could not be sent.",
            details: { fields: { body: "Write a message of up to 2,000 characters." } },
          },
        },
        { status: 422 },
      );
    }

    const { resource } = parsed.data;
    const lead =
      resource?.type === "lead" ? mockDb.leads.find((item) => item.id === resource.id) : undefined;
    if (resource !== null && lead === undefined) {
      return HttpResponse.json(
        {
          error: {
            code: "RESOURCE_NOT_FOUND",
            message: "The linked record no longer exists.",
          },
        },
        { status: 422 },
      );
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

  http.post(buildApiUrl("/conversations/:conversationId/read"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole())) return forbidden();

    const conversationId = String(params.conversationId);
    if (findConversation(conversationId) === undefined) {
      return conversationNotFound(conversationId);
    }

    mockDb.conversations = mockDb.conversations.map((conversation) =>
      conversation.id === conversationId ? { ...conversation, unread_count: 0 } : conversation,
    );
    const body: MarkConversationReadResponse = { data: { unread_total: unreadTotal() } };
    return HttpResponse.json(body);
  }),
];
