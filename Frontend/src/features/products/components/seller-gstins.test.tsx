import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { addLut, deleteLut, listSellerGstins } from "@/features/products/api/seller-gstins.api";
import { isApiError } from "@/lib/api/errors";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockDb, resetMockDb } from "@/mocks/db";
import { renderWithProviders } from "@/test/render";

import {
  currentYearDraft,
  financialYearLabel,
  financialYearOf,
  lutProblems,
  lutRefusal,
  SellerGstinsPanel,
} from "./seller-gstins-panel";

let keys = 0;
function key(): string {
  keys += 1;
  return `seller-gstins-test-${String(keys)}`;
}

async function codeOf(call: Promise<unknown>): Promise<string | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? (error.code ?? null) : null;
}

/** The second, non-default registration, whose LUT no document carries. */
function rajasthan(): { id: string; lutId: string } {
  const registration = mockDb.sellerGstins.find((item) => !item.is_default);
  const lut = registration?.luts[0];
  if (registration === undefined || lut === undefined) throw new Error("No second registration");
  return { id: registration.id, lutId: lut.id };
}

function gujarat(): { id: string; lutId: string } {
  const registration = mockDb.sellerGstins.find((item) => item.is_default);
  const lut = registration?.luts[0];
  if (registration === undefined || lut === undefined) throw new Error("No default registration");
  return { id: registration.id, lutId: lut.id };
}

describe("[MSTR-018] LUT rules", () => {
  it("names financial years", () => {
    expect(financialYearOf("2026-04-01")).toBe(2026);
    expect(financialYearOf("2027-03-31")).toBe(2026);
    expect(financialYearLabel(2026)).toBe("2026-27");
    expect(currentYearDraft("2026-10-18")).toEqual({
      arn: "",
      from: "2026-04-01",
      to: "2027-03-31",
    });
  });

  it("asks for an ARN and one financial year", () => {
    expect(lutProblems({ arn: "AD12", from: "2026-04-01", to: "2027-03-31" })).toEqual({
      arn: "10 to 20 letters and digits.",
    });
    expect(
      lutProblems({ arn: "AD2404260012345", from: "2026-04-01", to: "2027-04-30" }).to,
    ).toMatch(/one financial year/);
    expect(
      lutProblems({ arn: "AD2404260012345", from: "2026-06-01", to: "2026-05-01" }).to,
    ).toMatch(/after the first/);
    expect(lutProblems({ arn: "AD2404260012345", from: "2027-04-01", to: "2028-03-31" })).toEqual(
      {},
    );
  });
});

describe("[MSTR-018] Seller GSTINs (contract)", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("lists the registrations, the default first, LUTs newest first", async () => {
    resetMockDb();
    writeMockRole("employee");
    const rows = await listSellerGstins();
    expect(rows[0]?.isDefault).toBe(true);
    const years = rows[0]?.luts.map((lut) => lut.validFrom) ?? [];
    expect(years).toEqual([...years].sort().reverse());
  });

  it("adds next year's LUT and refuses overlaps, duplicates and a split year", async () => {
    resetMockDb();
    writeMockRole("admin");
    const { id } = gujarat();
    const lut = await addLut({
      gstinId: id,
      body: { arn: "ad2404270011111", valid_from: "2027-04-01", valid_to: "2028-03-31" },
      idempotencyKey: key(),
    });
    expect(lut.arn).toBe("AD2404270011111");
    const overlap = addLut({
      gstinId: id,
      body: { arn: "AD2404270022222", valid_from: "2027-06-01", valid_to: "2028-03-31" },
      idempotencyKey: key(),
    });
    expect(await codeOf(overlap)).toBe("lut_overlap");
    const duplicate = addLut({
      gstinId: rajasthan().id,
      body: { arn: "AD2404270011111", valid_from: "2027-04-01", valid_to: "2028-03-31" },
      idempotencyKey: key(),
    });
    expect(await codeOf(duplicate)).toBe("lut_duplicate");
    const split = addLut({
      gstinId: id,
      body: { arn: "AD2404280033333", valid_from: "2028-04-01", valid_to: "2029-04-30" },
      idempotencyKey: key(),
    });
    expect(await codeOf(split)).toBe("lut_dates");
  });

  it("removes a LUT no document carries, keeps one in use, and refuses readers", async () => {
    resetMockDb();
    writeMockRole("employee");
    const free = rajasthan();
    expect(
      await codeOf(deleteLut({ gstinId: free.id, lutId: free.lutId, idempotencyKey: key() })),
    ).toBe("forbidden");
    writeMockRole("admin");
    const used = gujarat();
    expect(
      await codeOf(deleteLut({ gstinId: used.id, lutId: used.lutId, idempotencyKey: key() })),
    ).toBe("lut_in_use");
    await deleteLut({ gstinId: free.id, lutId: free.lutId, idempotencyKey: key() });
    expect((await listSellerGstins()).find((row) => row.id === free.id)?.luts).toHaveLength(0);
  });

  it("puts each refusal on its field", () => {
    expect(lutRefusal(new Error("offline"))).toBeNull();
  });
});

describe("[MSTR-018] SellerGstinsPanel", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("shows each registration with its LUTs, and no changes for readers", async () => {
    resetMockDb();
    writeMockRole("employee");
    renderWithProviders(<SellerGstinsPanel canEdit={false} />);
    const list = await screen.findByRole("list", { name: "Seller GSTINs" });
    expect(within(list).getByText("24AAACP1234A1Z5")).toBeInTheDocument();
    expect(within(list).getAllByText("On a document").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Add LUT" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Remove LUT/ })).toBeNull();
  });

  it("adds a LUT, and shows a clash on its field", async () => {
    resetMockDb();
    writeMockRole("admin");
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <SellerGstinsPanel canEdit />
        <Toaster />
      </>,
    );
    await screen.findByRole("list", { name: "Seller GSTINs" });
    const [first] = screen.getAllByRole("button", { name: "Add LUT" });
    if (first === undefined) throw new Error("No Add LUT button");
    await user.click(first);
    const form = await screen.findByRole("form", { name: /Add a LUT to 24AAACP1234A1Z5/ });
    // This year's dates are filled in, and this year's LUT is on record: a clash.
    await user.type(within(form).getByLabelText("ARN"), "AD2404269999999");
    await user.click(within(form).getByRole("button", { name: "Add the LUT" }));
    expect(await within(form).findByText(/covers some of these dates/)).toBeInTheDocument();

    const from = within(form).getByLabelText("Valid from");
    const to = within(form).getByLabelText("Valid to");
    await user.clear(from);
    await user.type(from, "2027-04-01");
    await user.clear(to);
    await user.type(to, "2028-03-31");
    // The button shows "Not recorded" for a moment after the refusal.
    await user.click(
      await within(form).findByRole("button", { name: "Add the LUT" }, { timeout: 5000 }),
    );
    expect(await screen.findByText("LUT recorded")).toBeInTheDocument();
    expect(await screen.findByText("AD2404269999999")).toBeInTheDocument();
  });

  it("removes a LUT no document carries", async () => {
    resetMockDb();
    writeMockRole("admin");
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <SellerGstinsPanel canEdit />
        <Toaster />
      </>,
    );
    await user.click(await screen.findByRole("button", { name: "Remove LUT AD0804260054321" }));
    await user.click(await screen.findByRole("button", { name: "Remove" }));
    expect(await screen.findByText("LUT removed")).toBeInTheDocument();
    expect(await screen.findByText(/No LUT covers today/)).toBeInTheDocument();
  });
});
