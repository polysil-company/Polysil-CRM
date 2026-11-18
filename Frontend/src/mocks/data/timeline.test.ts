import { describe, expect, it } from "vitest";

import { timelinePageSchema } from "@/features/leads/api/leads.schemas";

import { generateLeads } from "./leads";
import { mockTimelineFor, newestFirst } from "./timeline";

describe("[LEAD-005] mock timelines", () => {
  const leads = generateLeads();

  function seeded(predicate: (lead: (typeof leads)[number]) => boolean): (typeof leads)[number] {
    const lead = leads.find(predicate);
    if (lead === undefined) {
      throw new Error("No matching seeded lead");
    }
    return lead;
  }

  it("match the backend's contract for every seeded lead", () => {
    for (const lead of leads) {
      const parsed = timelinePageSchema.safeParse({
        data: mockTimelineFor(lead),
        meta: { limit: 100, next_cursor: null },
      });
      expect(parsed.success, lead.inquiry_no).toBe(true);
      expect(parsed.data?.skipped, lead.inquiry_no).toBe(0);
    }
  });

  it("run newest first and start with the lead's creation", () => {
    for (const lead of leads) {
      const events = mockTimelineFor(lead);
      expect([...events].sort(newestFirst), lead.inquiry_no).toEqual(events);
      expect(events.at(-1)?.kind, lead.inquiry_no).toBe("lead.created");
    }
  });

  it("end a lost lead with its lost reason, and a merged lead with the merge", () => {
    const lost = seeded((lead) => lead.stage === "lost");
    const merged = seeded((lead) => lead.merged_into !== null);

    expect(mockTimelineFor(lost)[0]?.payload).toMatchObject({
      to: "lost",
      lost_reason_id: lost.lost_reason?.id,
    });
    expect(mockTimelineFor(merged).map((event) => event.kind)).toContain("lead.merged");
  });

  it("give every event a unique id", () => {
    const ids = leads.flatMap((lead) => mockTimelineFor(lead).map((event) => event.id));
    expect(new Set(ids).size).toBe(ids.length);
  });
});
