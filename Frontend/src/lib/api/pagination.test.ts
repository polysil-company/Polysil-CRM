import { describe, expect, it } from "vitest";
import { z } from "zod";

import { cursorPageSchema, pageMetaSchema } from "./pagination";

describe("[OBS-002] page metadata", () => {
  it("reads a middle page with a counted total", () => {
    expect(
      pageMetaSchema.parse({ limit: 25, next_cursor: "abc", total: 74, total_capped: false }),
    ).toEqual({ limit: 25, nextCursor: "abc", total: 74, totalCapped: false });
  });

  it("treats an absent cursor as the last page and an absent total as not counted", () => {
    expect(pageMetaSchema.parse({ limit: 50 })).toEqual({
      limit: 50,
      nextCursor: null,
      total: null,
      totalCapped: false,
    });
  });

  it("rejects metadata that breaks the contract", () => {
    expect(pageMetaSchema.safeParse({ limit: "25" }).success).toBe(false);
    expect(pageMetaSchema.safeParse({ limit: 25, total: -1 }).success).toBe(false);
  });
});

const rowSchema = z.object({ id: z.string().min(1), name: z.string().min(1) });
const pageSchema = cursorPageSchema(rowSchema);

describe("[OBS-002] cursor pages", () => {
  it("reads a clean page and counts nothing as skipped", () => {
    expect(
      pageSchema.parse({
        data: [
          { id: "1", name: "Ramesh" },
          { id: "2", name: "Meena" },
        ],
        meta: { limit: 25, next_cursor: "abc", total: 2 },
      }),
    ).toEqual({
      items: [
        { id: "1", name: "Ramesh" },
        { id: "2", name: "Meena" },
      ],
      nextCursor: "abc",
      total: 2,
      totalCapped: false,
      skipped: 0,
    });
  });

  it("leaves out a row that breaks the contract and keeps the rest", () => {
    const page = pageSchema.parse({
      data: [{ id: "1", name: "Ramesh" }, { id: "2" }, { id: "3", name: "" }],
      meta: { limit: 25 },
    });

    expect(page.items).toEqual([{ id: "1", name: "Ramesh" }]);
    expect(page.skipped).toBe(2);
  });

  it("treats a page where no row matches as a contract violation, naming the first failure", () => {
    const result = pageSchema.safeParse({ data: [{ id: 42 }], meta: { limit: 25 } });

    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toContain("no row of 1 matched the contract");
    expect(result.error?.issues[0]?.message).toContain("id:");
  });

  it("accepts an empty page, which is not a contract violation", () => {
    expect(pageSchema.parse({ data: [], meta: { limit: 25, total: 0 } })).toMatchObject({
      items: [],
      total: 0,
      skipped: 0,
    });
  });
});
