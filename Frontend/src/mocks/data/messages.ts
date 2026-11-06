import type { LeadWire } from "@/features/leads/api/leads.schemas";
import type {
  ConversationWire,
  MessageWire,
  PersonWire,
} from "@/features/messages/api/messages.schemas";

/** The staff user every staff sign-in becomes in the mock backend (see mockMeFor). */
export const MOCK_CURRENT_STAFF_ID = "usr-001";

/** Colleagues in the mock staff directory. */
export const MOCK_STAFF_DIRECTORY: readonly PersonWire[] = [
  {
    id: "usr-002",
    full_name: "Priya Nair",
    role_name: "District Manager",
    org_unit_name: "Vadodara District",
  },
  {
    id: "usr-003",
    full_name: "Rohan Mehta",
    role_name: "Employee",
    org_unit_name: "Vadodara Rural",
  },
  {
    id: "usr-004",
    full_name: "Kavita Joshi",
    role_name: "State Manager",
    org_unit_name: "Gujarat",
  },
  {
    id: "usr-005",
    full_name: "Sanjay Rao",
    role_name: "Account Manager",
    org_unit_name: "Head Office",
  },
  {
    id: "usr-006",
    full_name: "Neha Kulkarni",
    role_name: "Dispatch Manager",
    org_unit_name: "Head Office",
  },
  {
    id: "usr-007",
    full_name: "Imran Sheikh",
    role_name: "QA Manager",
    org_unit_name: "Head Office",
  },
  {
    id: "usr-008",
    full_name: "Anjali Verma",
    role_name: "Regional Manager",
    org_unit_name: "West Region",
  },
  {
    id: "usr-009",
    full_name: "Deepak Solanki",
    role_name: "Employee",
    org_unit_name: "Anand Rural",
  },
  {
    // Has left Polysil: the old conversation stays readable, the directory no longer lists her.
    id: "usr-010",
    full_name: "Meera Iyer",
    role_name: "Field Officer",
    org_unit_name: "Bharuch District",
    is_active: false,
  },
];

interface SeedMessage {
  readonly from: "me" | "them";
  readonly body: string;
  readonly minutesAgo: number;
  /** Index into the generated leads, to link a lead. */
  readonly leadIndex?: number;
}

interface SeedConversation {
  readonly id: string;
  readonly participantId: string;
  readonly unread: number;
  readonly messages: readonly SeedMessage[];
}

const CONVERSATION_SEEDS: readonly SeedConversation[] = [
  {
    id: "conv-001",
    participantId: "usr-002",
    unread: 2,
    messages: [
      {
        from: "them",
        body: "Morning Aarav — can you check the Karjan drip quotes before the review?",
        minutesAgo: 190,
      },
      { from: "me", body: "Yes, looking at them now.", minutesAgo: 175 },
      {
        from: "them",
        body: "This farmer has asked for a site visit this week.",
        minutesAgo: 14,
        leadIndex: 0,
      },
      { from: "them", body: "Can you take it? I'm in Anand till Thursday.", minutesAgo: 12 },
    ],
  },
  {
    id: "conv-002",
    participantId: "usr-003",
    unread: 1,
    messages: [
      {
        from: "them",
        body: "Added the acreage and crop details on this lead after today's call.",
        minutesAgo: 60,
        leadIndex: 1,
      },
    ],
  },
  {
    id: "conv-003",
    participantId: "usr-005",
    unread: 0,
    messages: [
      {
        from: "me",
        body: "Is the advance for Shah Agro Traders reflected yet?",
        minutesAgo: 1500,
      },
      {
        from: "them",
        body: "Received this morning — the ledger is updated.",
        minutesAgo: 1440,
      },
      { from: "me", body: "Thanks, I'll release the order.", minutesAgo: 1435 },
    ],
  },
  {
    id: "conv-004",
    participantId: "usr-006",
    unread: 0,
    messages: [
      {
        from: "them",
        body: "Dispatch for the Padra order goes out tomorrow at 7.",
        minutesAgo: 4400,
      },
      { from: "me", body: "Great, I'll let the dealer know.", minutesAgo: 4380 },
    ],
  },
  {
    id: "conv-005",
    participantId: "usr-010",
    unread: 0,
    messages: [
      {
        from: "them",
        body: "Handing my Bharuch leads to the district team before I leave on Friday.",
        minutesAgo: 20_000,
      },
      { from: "me", body: "Thanks Meera, all the best.", minutesAgo: 19_950 },
    ],
  },
];

export function findMockStaff(id: string): PersonWire | undefined {
  return MOCK_STAFF_DIRECTORY.find((person) => person.id === id);
}

/** How the backend names a lead linked from a message or notification: its inquiry number. */
export function mockLeadLabel(lead: LeadWire): string {
  return lead.inquiry_no;
}

function minutesAgo(now: number, minutes: number): string {
  return new Date(now - minutes * 60_000).toISOString();
}

/** Seeded conversations for the signed-in staff user, with a lead linked here and there. */
export function generateConversations(
  leads: readonly LeadWire[],
  now: number = Date.now(),
): { conversations: ConversationWire[]; messages: MessageWire[] } {
  const conversations: ConversationWire[] = [];
  const messages: MessageWire[] = [];

  for (const seed of CONVERSATION_SEEDS) {
    const participant = findMockStaff(seed.participantId);
    if (participant === undefined) {
      throw new Error(`Mock staff ${seed.participantId} is missing from the directory`);
    }

    const thread = seed.messages.map((entry, index): MessageWire => {
      const lead = entry.leadIndex === undefined ? undefined : leads[entry.leadIndex];
      return {
        id: `${seed.id}-msg-${String(index + 1)}`,
        conversation_id: seed.id,
        sender_id: entry.from === "me" ? MOCK_CURRENT_STAFF_ID : participant.id,
        body: entry.body,
        resource: lead ? { type: "lead", id: lead.id, label: mockLeadLabel(lead) } : null,
        created_at: minutesAgo(now, entry.minutesAgo),
      };
    });

    const last = thread.at(-1);
    messages.push(...thread);
    conversations.push({
      id: seed.id,
      kind: "direct",
      participant,
      last_message: last ?? null,
      unread_count: seed.unread,
      updated_at: last?.created_at ?? minutesAgo(now, 0),
    });
  }

  return { conversations, messages };
}

/** The signed-in staff user, as a group's member list names them. */
export const MOCK_CURRENT_STAFF_PERSON: PersonWire = {
  id: MOCK_CURRENT_STAFF_ID,
  full_name: "Aarav Desai",
  role_name: "State Manager",
  org_unit_name: "Gujarat",
  is_active: true,
};

/** Someone in a group, or who was (MSG-006). */
export interface MockGroupMember {
  readonly userId: string;
  addedAt: string;
  leftAt: string | null;
  isManager: boolean;
}

interface GroupSeed {
  readonly id: string;
  readonly name: string;
  readonly managerId: string;
  readonly memberIds: readonly string[];
  readonly unread: number;
  readonly messages: readonly { from: string; body: string; minutesAgo: number }[];
}

const GROUP_SEEDS: readonly GroupSeed[] = [
  {
    id: "grp-001",
    name: "Saurashtra sales",
    managerId: MOCK_CURRENT_STAFF_ID,
    memberIds: [MOCK_CURRENT_STAFF_ID, "usr-002", "usr-003", "usr-005"],
    unread: 1,
    messages: [
      {
        from: MOCK_CURRENT_STAFF_ID,
        body: "Morning all — let's close the Rajkot quotes this week.",
        minutesAgo: 300,
      },
      {
        from: "usr-002",
        body: "Two of mine are waiting on the farmer's land papers.",
        minutesAgo: 280,
      },
      { from: "usr-003", body: "I can visit Gondal on Thursday.", minutesAgo: 275 },
      { from: "usr-005", body: "Dispatch says the drip kits arrive Friday.", minutesAgo: 40 },
    ],
  },
  {
    id: "grp-002",
    name: "Dispatch coordination",
    managerId: "usr-005",
    memberIds: ["usr-005", MOCK_CURRENT_STAFF_ID, "usr-006"],
    unread: 0,
    messages: [],
  },
];

/** Seeded groups: one the user manages, with messages, and one someone else manages, empty. */
export function generateGroups(now: number = Date.now()): {
  conversations: ConversationWire[];
  messages: MessageWire[];
  members: Map<string, MockGroupMember[]>;
} {
  const conversations: ConversationWire[] = [];
  const messages: MessageWire[] = [];
  const members = new Map<string, MockGroupMember[]>();

  for (const seed of GROUP_SEEDS) {
    const thread = seed.messages.map((entry, index): MessageWire => ({
      id: `${seed.id}-msg-${String(index + 1)}`,
      conversation_id: seed.id,
      sender_id: entry.from,
      body: entry.body,
      resource: null,
      created_at: minutesAgo(now, entry.minutesAgo),
    }));
    messages.push(...thread);
    members.set(
      seed.id,
      seed.memberIds.map((userId, index) => ({
        userId,
        addedAt: minutesAgo(now, 60 * 24 * 10 - index),
        leftAt: null,
        isManager: userId === seed.managerId,
      })),
    );
    const last = thread.at(-1);
    conversations.push({
      id: seed.id,
      kind: "group",
      participant: null,
      group: {
        name: seed.name,
        member_count: seed.memberIds.length,
        manager_id: seed.managerId,
        i_manage: seed.managerId === MOCK_CURRENT_STAFF_ID,
      },
      last_message: last ?? null,
      unread_count: seed.unread,
      updated_at: last?.created_at ?? minutesAgo(now, 60 * 24 * 2),
    });
  }

  return { conversations, messages, members };
}
