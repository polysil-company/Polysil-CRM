import type { LeadWire, TimelineEventWire } from "@/features/leads/api/leads.schemas";
import { MOCK_ID_SPACE, MOCK_STAFF, mockUuid } from "@/mocks/data/reference";
import { mockTimelineFor } from "@/mocks/data/timeline";
import { mockDb } from "@/mocks/db";

/** The signed-in staff user in the mock (usr-001 in the session mock owns what they create). */
export const MOCK_CREATOR = MOCK_STAFF[0];

/**
 * A lead's timeline in the mock, newest first. The history derived from the seeded lead is
 * snapshotted on first use, so a later stage change adds one event rather than re-deriving
 * the whole walk from the new stage.
 */
export function leadEventsOf(lead: LeadWire): TimelineEventWire[] {
  const known = mockDb.leadEvents.get(lead.id);
  if (known !== undefined) {
    return known;
  }
  const derived = mockTimelineFor(lead);
  mockDb.leadEvents.set(lead.id, derived);
  return derived;
}

/** A new event written by the signed-in user, with the next mock event id. */
export function newMockEvent(kind: string, payload: Record<string, unknown>): TimelineEventWire {
  const event: TimelineEventWire = {
    id: mockUuid(MOCK_ID_SPACE.timeline, 900_000_000 + mockDb.writtenEvents),
    kind,
    occurred_at: new Date().toISOString(),
    actor: MOCK_CREATOR ?? null,
    payload: { actor_name: MOCK_CREATOR?.full_name ?? "", ...payload },
  };
  mockDb.writtenEvents += 1;
  return event;
}

/** Writes an event on the lead's timeline and marks the lead as just touched. */
export function recordLeadEvent(
  lead: LeadWire,
  kind: string,
  payload: Record<string, unknown>,
): TimelineEventWire {
  const event = newMockEvent(kind, payload);
  mockDb.leadEvents.set(lead.id, [event, ...leadEventsOf(lead)]);
  lead.last_activity_at = event.occurred_at;
  return event;
}
