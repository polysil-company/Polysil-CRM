import type { LeadWire } from "@/features/leads/api/leads.schemas";
import type { MinutesWire, TaskType, TaskWire } from "@/features/tasks/api/tasks.schemas";
import { todayInIndia } from "@/lib/format";

import { mockLookupRows } from "./lookups";
import { createRandom } from "./random";
import { MOCK_ID_SPACE, MOCK_PARTNERS, MOCK_STAFF, mockUuid } from "./reference";

/** A task as the mock keeps it: `overdue` is worked out when it is served, as on the backend. */
export type MockTask = Omit<TaskWire, "overdue">;

/** Minutes as the mock keeps them: action items by id, served as their tasks are now. */
export type MockMinutes = Omit<MinutesWire, "action_items"> & {
  readonly action_item_ids: readonly string[];
};

export interface MockUser {
  readonly id: string;
  readonly full_name: string;
}

/** The signed-in staff user in the mock session (`GET /auth/me`, usr-001). */
export const MOCK_TASK_ME: MockUser = { id: "usr-001", full_name: "Aarav Desai" };

/** The people below a manager in the mock: every other member of staff. */
export const MOCK_TEAM: readonly MockUser[] = MOCK_STAFF.filter(
  (person) => person.full_name !== MOCK_TASK_ME.full_name,
);

const DAY_MS = 24 * 60 * 60 * 1000;
const TIMES = ["09:30", "10:00", "11:00", "11:30", "12:30", "14:00", "15:30", "16:00", "17:30"];

const OUTCOMES = [
  "Spoke to him; he wants the revised quotation by Friday.",
  "Farm measured: 4.5 acres, borewell at the north corner.",
  "Showed the drip demo; family will decide after Diwali.",
  "Collected the 7/12 extract and Aadhaar copy.",
  "No answer; left a WhatsApp message.",
] as const;

/** A farmer's outcome for a task about a lead; a plain one for office work. */
function outcomeFor(aboutLead: boolean, farmerOutcome: string): string {
  return aboutLead ? farmerOutcome : "Done on time.";
}

const CANCEL_REASONS = [
  "The farmer went with another company.",
  "Covered in the meeting the day before.",
] as const;

/** One title per kind, about a farmer. */
function leadTitle(type: TaskType, lead: LeadWire, meetingName: string | null): string {
  switch (type) {
    case "call":
      return `Call ${lead.farmer_name} about the quotation`;
    case "visit":
      return `Visit ${lead.farmer_name}'s farm in ${lead.territory.name}`;
    case "meeting":
      return `${meetingName ?? "Meeting"} with ${lead.farmer_name}`;
    case "followup":
      return `Follow up with ${lead.farmer_name} on the subsidy papers`;
    case "other":
      return `Collect the 7/12 extract from ${lead.farmer_name}`;
  }
}

const UNLINKED_TITLES: Readonly<Record<TaskType, string>> = {
  call: "Call the transporter about Monday's dispatch",
  visit: "Visit the Rajkot warehouse for the stock count",
  meeting: "Monthly review with the district team",
  followup: "Send the weekly lead report",
  other: "Submit travel expenses for September",
};

/** "2026-10-03T10:30:00+05:30" for a day `offset` days from `now`, as an ISO instant. */
function dueAt(now: number, offset: number, time: string): string {
  const day = todayInIndia(new Date(now + offset * DAY_MS));
  return new Date(`${day}T${time}:00+05:30`).toISOString();
}

/**
 * Seeded tasks: a busy day for the signed-in user (some done, some still to do, a few overdue
 * from earlier in the week), and a spread of work for the five people below them, over the
 * past twelve days and the coming week. About half are about a lead; meetings on a lead carry
 * one of the backend's meeting types.
 */
export function generateTasks(leads: readonly LeadWire[], now: number = Date.now()): MockTask[] {
  const random = createRandom(0x7a5c);
  const openLeads = leads.filter((lead) => lead.stage !== "merged").slice(0, 40);
  const meetingTypes = mockLookupRows("meeting-types");
  const people: readonly MockUser[] = [MOCK_TASK_ME, ...MOCK_TEAM];
  const tasks: MockTask[] = [];

  const add = (
    index: number,
    assignee: MockUser,
    offset: number,
    time: string,
    type: TaskType,
    settle: boolean,
  ): void => {
    const linkRoll = random.next();
    const lead = linkRoll < 0.6 ? random.pick(openLeads) : null;
    const partner = lead === null && linkRoll < 0.75 ? random.pick(MOCK_PARTNERS) : null;
    const meetingType = type === "meeting" && lead !== null ? random.pick(meetingTypes) : undefined;
    const due = dueAt(now, offset, time);
    const past = Date.parse(due) < now;
    const roll = random.next();
    const status =
      settle && past ? (roll < 0.6 ? "done" : roll < 0.7 ? "cancelled" : "open") : "open";
    // A manager gives the team their work; the user gives themselves most of theirs.
    const assignedBy =
      assignee.id === MOCK_TASK_ME.id
        ? random.chance(0.3)
          ? MOCK_TEAM[0]
          : MOCK_TASK_ME
        : MOCK_TASK_ME;
    const created = new Date(Date.parse(due) - random.int(1, 5) * DAY_MS).toISOString();
    const completedAt =
      status === "done"
        ? new Date(Math.min(now, Date.parse(due) + 60 * 60 * 1000)).toISOString()
        : null;

    tasks.push({
      id: mockUuid(MOCK_ID_SPACE.task, index),
      title:
        lead !== null
          ? leadTitle(type, lead, meetingType?.name ?? null)
          : partner !== null
            ? `${type === "visit" ? "Visit" : "Call"} ${partner.name} about this month's stock`
            : UNLINKED_TITLES[type],
      task_type: type,
      status,
      due_at: due,
      assigned_to: { id: assignee.id, full_name: assignee.full_name },
      assigned_by:
        assignedBy === undefined ? null : { id: assignedBy.id, full_name: assignedBy.full_name },
      lead:
        lead === null
          ? null
          : {
              id: lead.id,
              hidden: false,
              inquiry_no: lead.inquiry_no,
              farmer_name: lead.farmer_name,
            },
      partner:
        partner === null
          ? null
          : {
              id: partner.id,
              hidden: false,
              name: partner.name,
              partner_type: partner.partner_type,
            },
      sales_order: null,
      meeting_type:
        meetingType === undefined
          ? null
          : { id: meetingType.id, code: meetingType.code, name: meetingType.name },
      minutes_id: null,
      // Draw every time, so the rest of the seed stays the same whatever the task is.
      notes:
        random.chance(0.5) && lead !== null && (type === "visit" || type === "meeting")
          ? "Carry the Polysil drip brochure and the subsidy checklist."
          : null,
      outcome: status === "done" ? outcomeFor(lead !== null, random.pick(OUTCOMES)) : null,
      gift_shown: status === "done" && type === "meeting" ? random.chance(0.5) : null,
      cancel_reason: status === "cancelled" ? random.pick(CANCEL_REASONS) : null,
      completed_at: completedAt,
      completed_by: status === "done" ? { id: assignee.id, full_name: assignee.full_name } : null,
      created_at: created,
      updated_at: completedAt ?? created,
    });
  };

  // The user's today: a full day, the morning's work done.
  const today: readonly (readonly [string, TaskType])[] = [
    ["09:30", "call"],
    ["11:00", "meeting"],
    ["12:30", "visit"],
    ["15:30", "followup"],
    ["17:30", "call"],
    ["18:00", "other"],
  ];
  today.forEach(([time, type], index) => {
    add(index + 1, MOCK_TASK_ME, 0, time, type, true);
  });
  // Left over from earlier in the week, still open: overdue.
  [-1, -2, -4].forEach((offset, index) => {
    add(today.length + index + 1, MOCK_TASK_ME, offset, random.pick(TIMES), "followup", false);
  });

  const first = today.length + 4;
  for (let index = 0; index < 60; index += 1) {
    const assignee = people[index % people.length] ?? MOCK_TASK_ME;
    const type = random.pick([
      "call",
      "visit",
      "meeting",
      "followup",
      "followup",
      "other",
    ] as const);
    add(first + index, assignee, random.int(-12, 6), random.pick(TIMES), type, true);
  }

  return tasks.sort((a, b) => a.due_at.localeCompare(b.due_at) || a.id.localeCompare(b.id));
}

/**
 * One seeded set of minutes, so a lead's page shows what recorded minutes look like: the
 * first done meeting on a lead, with two action items — one done, one still open.
 */
export function seedMinutes(
  tasks: readonly MockTask[],
  now: number = Date.now(),
): { tasks: MockTask[]; minutes: MockMinutes[] } {
  const meeting = tasks.find(
    (task) => task.task_type === "meeting" && task.status === "done" && task.lead !== null,
  );
  if (meeting === undefined || meeting.lead === null || meeting.assigned_to === null) {
    return { tasks: [...tasks], minutes: [] };
  }
  const minutesId = mockUuid(MOCK_ID_SPACE.task, 0x8000);
  const owner = meeting.assigned_to;
  const base = {
    assigned_to: owner,
    assigned_by: owner,
    lead: meeting.lead,
    partner: null,
    sales_order: null,
    meeting_type: null,
    minutes_id: minutesId,
    notes: null,
    gift_shown: null,
    cancel_reason: null,
    created_at: meeting.due_at,
  } as const;
  const sendQuote: MockTask = {
    ...base,
    id: mockUuid(MOCK_ID_SPACE.task, 0x8001),
    title: "Send the revised quotation with the 16 mm lateral",
    task_type: "followup",
    status: "done",
    due_at: new Date(Date.parse(meeting.due_at) + DAY_MS).toISOString(),
    outcome: "Sent on WhatsApp.",
    completed_at: new Date(Date.parse(meeting.due_at) + DAY_MS).toISOString(),
    completed_by: owner,
    updated_at: new Date(Date.parse(meeting.due_at) + DAY_MS).toISOString(),
  };
  const subsidy: MockTask = {
    ...base,
    id: mockUuid(MOCK_ID_SPACE.task, 0x8002),
    title: "Collect the subsidy papers: 7/12 extract and bank passbook",
    task_type: "visit",
    status: "open",
    due_at: dueAt(now, 2, "11:00"),
    outcome: null,
    completed_at: null,
    completed_by: null,
    updated_at: meeting.due_at,
  };
  const minutes: MockMinutes = {
    id: minutesId,
    lead: meeting.lead,
    partner: null,
    task_id: meeting.id,
    held_at: meeting.due_at,
    attendees: [meeting.lead.farmer_name ?? "The farmer", "His son", owner.full_name],
    notes:
      "Walked the plot with the family. They want drip on 3 acres of cotton now and the rest after the monsoon. Price is fine if the subsidy comes through.",
    created_by: owner,
    created_at: meeting.due_at,
    action_item_ids: [sendQuote.id, subsidy.id],
  };
  return {
    tasks: [...tasks, sendQuote, subsidy].sort(
      (a, b) => a.due_at.localeCompare(b.due_at) || a.id.localeCompare(b.id),
    ),
    minutes: [minutes],
  };
}
