import type { LeadStage, LeadWire, TimelineEventWire } from "@/features/leads/api/leads.schemas";

import { MOCK_ID_SPACE, MOCK_STAFF, mockUuid } from "./reference";

/** The path a lead walks through the backend's stage machine (api/domain/leads.py). */
const STAGE_PATH: readonly LeadStage[] = ["new", "contacted", "qualified", "quoted", "negotiation"];

const MINUTE = 60 * 1000;

function iso(ms: number): string {
  return new Date(ms).toISOString();
}

/** A stable event id per lead and step, in its own UUID space. */
function eventId(lead: LeadWire, step: number): string {
  const leadNumber = Number(lead.inquiry_no.split("/").at(-1) ?? "0");
  return mockUuid(MOCK_ID_SPACE.timeline, leadNumber * 100 + step);
}

function actorOf(lead: LeadWire): { id: string; full_name: string } | null {
  return lead.owner ?? lead.created_by ?? MOCK_STAFF[0] ?? null;
}

/**
 * LEAD-005 · A believable history for a seeded lead, derived from the lead itself so it
 * always agrees with the lead page: created → each stage it passed → lost or merged, plus
 * a duplicate flag. Newest first, as the backend returns it. Notes added through the mock
 * and stage changes made through the mock are kept in `mockDb.leadEvents` and merged in
 * by the handler.
 */
export function mockTimelineFor(lead: LeadWire): TimelineEventWire[] {
  const createdAt = Date.parse(lead.created_at);
  const lastActivityAt = Math.max(createdAt + MINUTE, Date.parse(lead.last_activity_at));
  const creator = lead.created_by;
  const actor = actorOf(lead);
  const events: TimelineEventWire[] = [
    {
      id: eventId(lead, 0),
      kind: "lead.created",
      occurred_at: iso(createdAt),
      actor: creator,
      payload: {
        actor_name: creator?.full_name ?? "",
        stage: "new",
        source: lead.source,
        inquiry_no: lead.inquiry_no,
      },
    },
  ];

  const pending = (lead.duplicates ?? []).filter((duplicate) => duplicate.state === "pending");
  if (pending.length > 0) {
    events.push({
      id: eventId(lead, 1),
      kind: "lead.duplicate_flagged",
      occurred_at: iso(createdAt + MINUTE),
      actor: creator,
      payload: {
        actor_name: creator?.full_name ?? "",
        matches: pending.map((duplicate) => ({
          lead_id: duplicate.lead_id,
          signal: duplicate.signal,
          score: duplicate.score ?? "1.00",
        })),
      },
    });
  }

  // Walk the stage path up to the lead's stage; a won, lost or merged lead walked part of it.
  const reached = STAGE_PATH.indexOf(lead.stage);
  const walked = reached >= 0 ? reached : lead.stage === "won" ? STAGE_PATH.length - 1 : 1;
  const finalMove = lead.stage === "won" || lead.stage === "lost" ? 1 : 0;
  const steps = walked + finalMove;
  const span = lastActivityAt - createdAt;

  for (let step = 1; step <= walked; step += 1) {
    const from = STAGE_PATH[step - 1];
    const to = STAGE_PATH[step];
    if (from === undefined || to === undefined) {
      break;
    }
    events.push({
      id: eventId(lead, 10 + step),
      kind: "lead.stage_changed",
      occurred_at: iso(createdAt + (span * step) / (steps + 1)),
      actor,
      payload: { actor_name: actor?.full_name ?? "", from, to },
    });
  }

  if (finalMove === 1) {
    const from = STAGE_PATH[walked] ?? "contacted";
    events.push({
      id: eventId(lead, 20),
      kind: "lead.stage_changed",
      occurred_at: iso(lastActivityAt),
      actor,
      payload: {
        actor_name: actor?.full_name ?? "",
        from,
        to: lead.stage,
        ...(lead.stage === "lost"
          ? { lost_reason_id: lead.lost_reason?.id ?? null, lost_note: lead.lost_note }
          : {}),
      },
    });
  }

  if (lead.merged_into !== null) {
    events.push({
      id: eventId(lead, 30),
      kind: "lead.merged",
      occurred_at: iso(lastActivityAt),
      actor,
      payload: {
        actor_name: actor?.full_name ?? "",
        loser: lead.id,
        survivor: lead.merged_into.id,
      },
    });
  }

  return events.sort(newestFirst);
}

/** Newest first, ties broken by id — the backend's keyset order. */
export function newestFirst(a: TimelineEventWire, b: TimelineEventWire): number {
  return Date.parse(b.occurred_at) - Date.parse(a.occurred_at) || b.id.localeCompare(a.id);
}
