import { afterEach, describe, expect, it } from "vitest";

import { listLookup } from "@/features/lookups/api/lookups.api";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { resetMockDb } from "@/mocks/db";

import { addLookupItem, getScoring, patchScoring, updateLookupItem } from "./masters.api";

async function failureOf(request: Promise<unknown>): Promise<unknown> {
  try {
    await request;
  } catch (error) {
    return error;
  }
  throw new Error("Expected the request to fail");
}

function reset(): void {
  resetMockDb();
  writeMockRole("state_manager");
}

describe("[MSTR-009] The admin lists", () => {
  afterEach(reset);

  it("adds a row that every reader of the list then sees", async () => {
    writeMockRole("admin");
    const added = await addLookupItem("lead-sources", {
      code: "krishi_mela",
      name: "Krishi Mela",
      sort_order: 15,
      quality: "0.6",
    });

    expect(added).toMatchObject({ code: "krishi_mela", name: "Krishi Mela", isActive: true });
    expect((await listLookup("lead-sources")).some((row) => row.code === "krishi_mela")).toBe(true);
  });

  it("refuses a code already in use, on its field", async () => {
    writeMockRole("admin");
    const error = await failureOf(addLookupItem("crops", { code: "cotton", name: "Cotton 2" }));
    expect(readFieldErrors(error)).toEqual({ code: "already in use" });
  });

  it("switches a row off and on, keeping it in the list", async () => {
    writeMockRole("admin");
    const [first] = await listLookup("lost-reasons");
    if (first === undefined) throw new Error("No lost reasons");

    const off = await updateLookupItem("lost-reasons", first.id, { is_active: false });
    expect(off.isActive).toBe(false);
    expect((await listLookup("lost-reasons")).find((row) => row.id === first.id)?.isActive).toBe(
      false,
    );
    expect((await updateLookupItem("lost-reasons", first.id, { is_active: true })).isActive).toBe(
      true,
    );
  });

  it("is refused to someone without masters.edit", async () => {
    writeMockRole("employee");
    const error = await failureOf(addLookupItem("crops", { code: "jowar", name: "Jowar" }));
    expect(isApiError(error) && error.status).toBe(403);
  });
});

describe("[MSTR-010] Lead scoring", () => {
  afterEach(reset);

  it("reads every setting, and changes only those sent", async () => {
    const before = await getScoring();
    expect(before.find((item) => item.key === "threshold_hot")?.value).toBe("70.00");

    writeMockRole("admin");
    const after = await patchScoring({ values: { threshold_hot: "75" } });
    expect(after.find((item) => item.key === "threshold_hot")?.value).toBe("75.00");
    expect(after.find((item) => item.key === "w_value")?.value).toBe("35.00");
  });

  it("refuses a cap of zero and an unknown key, naming each", async () => {
    writeMockRole("admin");
    const error = await failureOf(patchScoring({ values: { value_cap: "0", w_magic: "5" } }));
    expect(readFieldErrors(error)).toEqual({
      value_cap: "must be more than 0",
      w_magic: "unknown setting",
    });
  });
});
