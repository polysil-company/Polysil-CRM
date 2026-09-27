import { describe, expect, it } from "vitest";

import type { TimelineEvent } from "@/features/leads/api/leads.schemas";

import { joinFields, labelForUnknownKind, toTimelineEntry } from "./timeline-entries";

const LEAD_ID = "lead-1";

function event(kind: string, payload: Record<string, unknown> = {}): TimelineEvent {
  return {
    id: `evt-${kind}`,
    kind,
    occurredAt: "2026-09-20T10:00:00+05:30",
    actor: { id: "usr-1", name: "Asha Patel" },
    payload,
  };
}

describe("[LEAD-005] toTimelineEntry", () => {
  it("reads a created lead with its source", () => {
    expect(toTimelineEntry(event("lead.created", { source: "agri_fair" }), LEAD_ID)).toEqual({
      type: "created",
      source: "agri_fair",
    });
  });

  it("reads a note, and falls back to a label when the text is missing", () => {
    expect(
      toTimelineEntry(event("lead.note_added", { note: "Called, wants drip" }), LEAD_ID),
    ).toEqual({
      type: "note",
      note: "Called, wants drip",
    });
    expect(toTimelineEntry(event("lead.note_added", { note: "   " }), LEAD_ID)).toEqual({
      type: "other",
      label: "Note added",
    });
  });

  it("reads a stage change, with the lost reason and note on a lost lead", () => {
    expect(
      toTimelineEntry(
        event("lead.stage_changed", {
          from: "qualified",
          to: "lost",
          lost_reason_id: "reason-9",
          lost_note: "Bought from a competitor",
        }),
        LEAD_ID,
      ),
    ).toEqual({
      type: "stage",
      from: "qualified",
      to: "lost",
      lostReasonId: "reason-9",
      lostNote: "Bought from a competitor",
    });
  });

  it("reads a stage the frontend does not know as null rather than dropping the event", () => {
    expect(
      toTimelineEntry(event("lead.stage_changed", { from: 3, to: "archived" }), LEAD_ID),
    ).toEqual({ type: "stage", from: null, to: null, lostReasonId: null, lostNote: null });
  });

  it("reads a reopening with its note", () => {
    expect(
      toTimelineEntry(
        event("lead.reopened", { from: "lost", to: "contacted", note: "Back" }),
        LEAD_ID,
      ),
    ).toEqual({ type: "reopened", to: "contacted", note: "Back" });
  });

  it("tells a set owner from a cleared one, and leaves an untouched partner alone", () => {
    expect(toTimelineEntry(event("lead.assigned", { owner_user_id: "usr-2" }), LEAD_ID)).toEqual({
      type: "assigned",
      owner: "set",
      partner: "unchanged",
    });
    expect(
      toTimelineEntry(
        event("lead.assigned", { owner_user_id: null, assigned_partner_id: "p-1" }),
        LEAD_ID,
      ),
    ).toEqual({ type: "assigned", owner: "cleared", partner: "set" });
  });

  it("names the edited fields in words", () => {
    expect(
      toTimelineEntry(
        event("lead.updated", { changed: { farmer_name: "A", territory_id: "t", crop_type: "x" } }),
        LEAD_ID,
      ),
    ).toEqual({ type: "updated", fields: ["farmer name", "territory", "Crop type"] });
    expect(toTimelineEntry(event("lead.updated", { changed: "oops" }), LEAD_ID)).toEqual({
      type: "updated",
      fields: [],
    });
  });

  it("reads a merge from the side of the lead on screen", () => {
    const merge = { survivor: LEAD_ID, loser: "lead-2" };
    expect(toTimelineEntry(event("lead.merged", merge), LEAD_ID)).toEqual({
      type: "merged",
      role: "survivor",
      otherLeadId: "lead-2",
    });
    expect(toTimelineEntry(event("lead.merged", merge), "lead-2")).toEqual({
      type: "merged",
      role: "loser",
      otherLeadId: LEAD_ID,
    });
    expect(toTimelineEntry(event("lead.merged", merge), "lead-3")).toEqual({
      type: "other",
      label: "Leads merged",
    });
  });

  it("counts flagged duplicates, and reads dismissals and deletion", () => {
    expect(
      toTimelineEntry(event("lead.duplicate_flagged", { matches: [{}, {}] }), LEAD_ID),
    ).toEqual({ type: "duplicate-flagged", count: 2 });
    expect(toTimelineEntry(event("lead.duplicate_dismissed"), LEAD_ID)).toEqual({
      type: "duplicate-dismissed",
    });
    expect(toTimelineEntry(event("lead.deleted"), LEAD_ID)).toEqual({ type: "deleted" });
  });

  it("labels quotation, order and unknown events instead of hiding them", () => {
    expect(toTimelineEntry(event("quotation.sent"), LEAD_ID)).toEqual({
      type: "other",
      label: "Quotation sent",
    });
    expect(labelForUnknownKind("subsidy.case_opened")).toBe("Subsidy case opened");
  });
});

describe("[LEAD-005] joinFields", () => {
  it("joins field names as a sentence does", () => {
    expect(joinFields([])).toBe("");
    expect(joinFields(["mobile"])).toBe("mobile");
    expect(joinFields(["mobile", "email"])).toBe("mobile and email");
    expect(joinFields(["farmer name", "mobile", "village"])).toBe(
      "farmer name, mobile and village",
    );
  });
});
