import { afterEach, describe, expect, it } from "vitest";

import { listLookup } from "@/features/lookups/api/lookups.api";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { resetMockDb } from "@/mocks/db";

import {
  addLookupItem,
  createOffice,
  getScoring,
  listOffices,
  patchOffice,
  patchScoring,
  setOfficeOpen,
  updateLookupItem,
} from "./masters.api";

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

describe("[MSTR-011] Offices", () => {
  afterEach(reset);

  async function officeNamed(name: string): Promise<{ id: string; activeUsers: number }> {
    const page = await listOffices({ q: name, state: "all", cursor: null });
    const office = page.items.find((item) => item.name === name);
    if (office === undefined) throw new Error(`No ${name}`);
    return office;
  }

  it("lists open offices by default, closed ones when asked, with their people", async () => {
    const open = await listOffices({ q: "", state: "open", cursor: null });
    expect(open.items.every((office) => office.isOpen)).toBe(true);
    const closed = await listOffices({ q: "", state: "closed", cursor: null });
    expect(closed.items.map((office) => office.name)).toEqual(["Bhavnagar District (closed)"]);
    expect((await officeNamed("Rajkot District")).activeUsers).toBe(2);
  });

  it("adds an office under an open one, refusing a name used beside it", async () => {
    writeMockRole("admin");
    const state = await officeNamed("Gujarat State");
    const made = await createOffice({
      name: "Kutch District",
      role_level: 2,
      parent_id: state.id,
      territory_id: null,
    });
    expect(made).toMatchObject({ name: "Kutch District", isOpen: true, activeUsers: 0 });
    expect(made.parent?.name).toBe("Gujarat State");

    const error = await failureOf(
      createOffice({
        name: "rajkot district",
        role_level: 2,
        parent_id: state.id,
        territory_id: null,
      }),
    );
    expect(readFieldErrors(error)).toEqual({ name: "already used beside it" });
  });

  it("refuses a move under one of its own offices", async () => {
    writeMockRole("admin");
    const state = await officeNamed("Gujarat State");
    const rajkot = await officeNamed("Rajkot District");
    const error = await failureOf(patchOffice(state.id, { parent_id: rajkot.id }));
    expect(readFieldErrors(error)).toEqual({
      parent_id: "an office can't sit under itself or one of its own",
    });
  });

  it("won't close an office people work from; closes and reopens an empty one", async () => {
    writeMockRole("admin");
    const rajkot = await officeNamed("Rajkot District");
    const refused = await failureOf(setOfficeOpen(rajkot.id, false));
    expect(readFieldErrors(refused)).toHaveProperty("id");

    const empty = await createOffice({
      name: "Morbi District",
      role_level: 2,
      parent_id: null,
      territory_id: null,
    });
    expect((await setOfficeOpen(empty.id, false)).isOpen).toBe(false);
    expect((await setOfficeOpen(empty.id, true)).isOpen).toBe(true);
  });

  it("is refused to someone without masters.edit", async () => {
    writeMockRole("employee");
    const error = await failureOf(
      createOffice({ name: "X", role_level: 1, parent_id: null, territory_id: null }),
    );
    expect(isApiError(error) && error.status).toBe(403);
  });
});
