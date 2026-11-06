import { z } from "zod";

import type { ResourceRef } from "@/lib/navigation/resource-href";

/**
 * MSG-001 … MSG-006 · Messages between staff, one to one or in named groups, as the backend
 * serves them since BE-010 and FS-048 (backend/docs/api/messages.md). Staff only: the backend
 * answers partner users with 403. There is no push: the list and the open conversation poll.
 */

const isoDateTime = z.iso.datetime({ offset: true });
const count = z.number().int().nonnegative();

/** Longest message the backend takes (`MESSAGE_MAX` in backend/api/schemas/messages.py). */
export const MESSAGE_MAX_LENGTH = 2000;

export const personWireSchema = z.object({
  id: z.string().min(1),
  full_name: z.string().min(1),
  role_name: z.string().nullish(),
  org_unit_name: z.string().nullish(),
  /** False for a colleague who has left: the history stays readable, a new message is refused. */
  is_active: z.boolean().optional(),
});

export type PersonWire = z.input<typeof personWireSchema>;

const resourceWireSchema = z.object({
  type: z.string().min(1),
  id: z.string().min(1),
  label: z.string().min(1),
});

export const messageWireSchema = z.object({
  id: z.string().min(1),
  conversation_id: z.string().min(1),
  sender_id: z.string().min(1),
  body: z.string().min(1),
  resource: resourceWireSchema.nullish(),
  created_at: isoDateTime,
});

export type MessageWire = z.input<typeof messageWireSchema>;

/** Group size limits: up to 49 colleagues besides the user at the start, 50 in all. */
export const GROUP_NAME_MAX_LENGTH = 80;
export const GROUP_MAX_MEMBERS = 50;

const groupInfoWireSchema = z.object({
  name: z.string().min(1),
  /** Members in the group now. */
  member_count: count,
  /** Who renames and removes. Null only when nobody active is left to manage it. */
  manager_id: z.string().min(1).nullable(),
  i_manage: z.boolean(),
});

export const conversationWireSchema = z
  .object({
    id: z.string().min(1),
    /** direct: one to one. group: a named group (MSG-006). Older answers leave it out. */
    kind: z.enum(["direct", "group"]).default("direct"),
    /** The other person, for a direct conversation; null for a group. */
    participant: personWireSchema.nullable(),
    group: groupInfoWireSchema.nullish(),
    last_message: messageWireSchema.nullish(),
    /** Messages the signed-in user has not read yet. */
    unread_count: count,
    updated_at: isoDateTime,
  })
  .superRefine((wire, context) => {
    if (wire.kind === "direct" && wire.participant === null) {
      context.addIssue({
        code: "custom",
        path: ["participant"],
        message: "a direct conversation names its participant",
      });
    }
    if (wire.kind === "group" && (wire.group === undefined || wire.group === null)) {
      context.addIssue({ code: "custom", path: ["group"], message: "a group carries its group" });
    }
  });

export type ConversationWire = z.input<typeof conversationWireSchema>;

export interface Person {
  readonly id: string;
  readonly name: string;
  readonly roleName: string | null;
  readonly orgUnitName: string | null;
  /** False once they have left Polysil: their messages stay, new ones are refused. */
  readonly isActive: boolean;
}

export interface Message {
  readonly id: string;
  readonly conversationId: string;
  readonly senderId: string;
  readonly body: string;
  readonly resource: ResourceRef | null;
  readonly createdAt: string;
}

export interface GroupInfo {
  readonly name: string;
  readonly memberCount: number;
  /** Null only when nobody active is left to manage it. */
  readonly managerId: string | null;
  /** The signed-in user manages it: renames, and removes members. */
  readonly iManage: boolean;
}

interface ConversationBase {
  readonly id: string;
  readonly lastMessage: Message | null;
  readonly unreadCount: number;
  readonly updatedAt: string;
}

export interface DirectConversation extends ConversationBase {
  readonly kind: "direct";
  readonly participant: Person;
  readonly group: null;
}

export interface GroupConversation extends ConversationBase {
  readonly kind: "group";
  readonly participant: null;
  readonly group: GroupInfo;
}

/** One to one, or a named group (MSG-006). */
export type Conversation = DirectConversation | GroupConversation;

/** What a conversation is called: the colleague's name, or the group's. */
export function conversationName(conversation: Conversation): string {
  return conversation.kind === "group" ? conversation.group.name : conversation.participant.name;
}

/** MSG-006 · Someone who is, or was, in a group. */
export interface Member {
  readonly person: Person;
  readonly addedAt: string;
  /** Set once they have left the group, or been removed. */
  readonly leftAt: string | null;
  readonly isManager: boolean;
}

export interface ConversationList {
  /** Most recent activity first. */
  readonly items: readonly Conversation[];
  readonly unreadTotal: number;
}

export interface MessagePage {
  /** Oldest first, so the thread reads top to bottom. */
  readonly items: readonly Message[];
  /** For loading older messages. */
  readonly nextCursor: string | null;
}

export interface MarkConversationReadResult {
  readonly unreadTotal: number;
}

function toPerson(wire: z.output<typeof personWireSchema>): Person {
  return {
    id: wire.id,
    name: wire.full_name,
    roleName: wire.role_name ?? null,
    orgUnitName: wire.org_unit_name ?? null,
    isActive: wire.is_active ?? true,
  };
}

function toMessage(wire: z.output<typeof messageWireSchema>): Message {
  return {
    id: wire.id,
    conversationId: wire.conversation_id,
    senderId: wire.sender_id,
    body: wire.body,
    resource: wire.resource ?? null,
    createdAt: wire.created_at,
  };
}

function toConversation(wire: z.output<typeof conversationWireSchema>): Conversation {
  const base = {
    id: wire.id,
    lastMessage: wire.last_message ? toMessage(wire.last_message) : null,
    unreadCount: wire.unread_count,
    updatedAt: wire.updated_at,
  };
  // The schema has checked that a group carries its group and a pair its participant.
  if (wire.kind === "group" && wire.group) {
    return {
      ...base,
      kind: "group",
      participant: null,
      group: {
        name: wire.group.name,
        memberCount: wire.group.member_count,
        managerId: wire.group.manager_id,
        iManage: wire.group.i_manage,
      },
    };
  }
  if (wire.participant === null) {
    throw new Error("A direct conversation without its participant passed the schema");
  }
  return { ...base, kind: "direct", participant: toPerson(wire.participant), group: null };
}

/** MSG-001 · GET /conversations */
export const conversationListResponseSchema = z
  .object({ data: z.array(conversationWireSchema), meta: z.object({ unread_total: count }) })
  .transform(({ data, meta }): ConversationList => ({
    items: data.map(toConversation),
    unreadTotal: meta.unread_total,
  }));

export type ConversationListResponse = z.input<typeof conversationListResponseSchema>;

/** MSG-004 · POST /conversations */
export const conversationResponseSchema = z
  .object({ data: conversationWireSchema })
  .transform(({ data }): Conversation => toConversation(data));

export type ConversationResponse = z.input<typeof conversationResponseSchema>;

/** MSG-002 · GET /conversations/{conversationId}/messages */
export const messageListResponseSchema = z
  .object({
    data: z.array(messageWireSchema),
    meta: z.object({ next_cursor: z.string().nullish() }),
  })
  .transform(({ data, meta }): MessagePage => ({
    items: data.map(toMessage),
    nextCursor: meta.next_cursor ?? null,
  }));

export type MessageListResponse = z.input<typeof messageListResponseSchema>;

/** MSG-003 · POST /conversations/{conversationId}/messages */
export const messageResponseSchema = z
  .object({ data: messageWireSchema })
  .transform(({ data }): Message => toMessage(data));

export type MessageResponse = z.input<typeof messageResponseSchema>;

/** MSG-004 · GET /staff-directory — colleagues the user can message. Never includes the user. */
export const staffDirectoryResponseSchema = z
  .object({ data: z.array(personWireSchema) })
  .transform(({ data }): readonly Person[] => data.map(toPerson));

export type StaffDirectoryResponse = z.input<typeof staffDirectoryResponseSchema>;

/** MSG-005 · POST /conversations/{conversationId}/read */
export const markConversationReadResponseSchema = z
  .object({ data: z.object({ unread_total: count }) })
  .transform(({ data }): MarkConversationReadResult => ({ unreadTotal: data.unread_total }));

export type MarkConversationReadResponse = z.input<typeof markConversationReadResponseSchema>;

/** MSG-003 request body. The backend resolves the record's label from its type and id. */
export const sendMessageRequestSchema = z.object({
  body: z.string().trim().min(1).max(MESSAGE_MAX_LENGTH),
  resource: z.object({ type: z.string().min(1), id: z.string().min(1) }).nullable(),
});

export type SendMessageRequest = z.input<typeof sendMessageRequestSchema>;

/**
 * MSG-005 request body. `up_to` is the newest message on screen, so one that arrives while
 * the call runs stays unread; left out, everything so far is read.
 */
export interface MarkConversationReadRequest {
  readonly up_to?: string;
}

/** MSG-004 request body. Returns the existing conversation when there already is one. */
export const startConversationRequestSchema = z.object({ participant_id: z.string().min(1) });

export type StartConversationRequest = z.infer<typeof startConversationRequestSchema>;

/** MSG-006 · One member of a group, as the backend lists them. */
export const memberWireSchema = z.object({
  person: personWireSchema,
  added_at: isoDateTime,
  left_at: isoDateTime.nullable(),
  is_manager: z.boolean(),
});

/** MSG-006 · GET and POST /conversations/{id}/members: everyone who has been in it, current first. */
export const memberListResponseSchema = z
  .object({ data: z.array(memberWireSchema) })
  .transform(({ data }): readonly Member[] =>
    data.map((wire) => ({
      person: toPerson(wire.person),
      addedAt: wire.added_at,
      leftAt: wire.left_at,
      isManager: wire.is_manager,
    })),
  );

export type MemberListResponse = z.input<typeof memberListResponseSchema>;

/** MSG-006 · POST /conversations/groups: a name, and 1 to 49 colleagues besides the user. */
export const createGroupRequestSchema = z.object({
  name: z.string().trim().min(1).max(GROUP_NAME_MAX_LENGTH),
  member_ids: z
    .array(z.string().min(1))
    .min(1)
    .max(GROUP_MAX_MEMBERS - 1),
});

export type CreateGroupRequest = z.infer<typeof createGroupRequestSchema>;

/** MSG-006 · PATCH /conversations/{id}: the manager renames the group. */
export const renameGroupRequestSchema = z.object({
  name: z.string().trim().min(1).max(GROUP_NAME_MAX_LENGTH),
});

export type RenameGroupRequest = z.infer<typeof renameGroupRequestSchema>;

/** MSG-006 · POST /conversations/{id}/members. Someone already in is ignored. */
export const addMembersRequestSchema = z.object({ user_ids: z.array(z.string().min(1)).min(1) });

export type AddMembersRequest = z.infer<typeof addMembersRequestSchema>;
