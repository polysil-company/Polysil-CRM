import type { Lead } from "@/features/leads/api/leads.schemas";
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
];

export function findMockStaff(id: string): PersonWire | undefined {
  return MOCK_STAFF_DIRECTORY.find((person) => person.id === id);
}

/** How a lead is named when it is linked from a message or notification. */
export function mockLeadLabel(lead: Lead): string {
  return `${lead.customerName} · ${lead.code}`;
}

function minutesAgo(now: number, minutes: number): string {
  return new Date(now - minutes * 60_000).toISOString();
}

/** Seeded conversations for the signed-in staff user, with a lead linked here and there. */
export function generateConversations(
  leads: readonly Lead[],
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
      participant,
      last_message: last ?? null,
      unread_count: seed.unread,
      updated_at: last?.created_at ?? minutesAgo(now, 0),
    });
  }

  return { conversations, messages };
}
