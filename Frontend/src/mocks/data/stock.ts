import type { MovementWire, WarehouseWire } from "@/features/stock/api/stock.schemas";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";

import type { MockProductRecord } from "./products";
import { mockUuid } from "./reference";

/** The mock's own id space for warehouses and stock movements. */
const STOCK_SPACE = 0x570c;

export function mockStockId(kind: number, index: number): string {
  return mockUuid(STOCK_SPACE, kind * 10_000 + index);
}

/** Ahmedabad is the default; Rajkot holds less; the old Surat godown is switched off. */
export function seedWarehouses(): WarehouseWire[] {
  return [
    {
      id: mockStockId(1, 1),
      code: "AHD-1",
      name: "Ahmedabad depot",
      territory_id: null,
      is_default: true,
      is_active: true,
    },
    {
      id: mockStockId(1, 2),
      code: "RJT-1",
      name: "Rajkot depot",
      territory_id: null,
      is_default: false,
      is_active: true,
    },
    {
      id: mockStockId(1, 3),
      code: "SRT-OLD",
      name: "Surat godown (closed)",
      territory_id: null,
      is_default: false,
      is_active: false,
    },
  ];
}

const KEEPER = { id: "usr-dispatch", full_name: "Ramesh Vaghela" };

/**
 * Opening balances for the first twelve products in both depots, a later receipt and one
 * correction in Ahmedabad. Rajkot holds a tenth of Ahmedabad, so open orders leave some short.
 */
export function seedMovements(
  products: readonly MockProductRecord[],
  warehouses: readonly WarehouseWire[],
): MovementWire[] {
  const [ahmedabad, rajkot] = warehouses;
  if (ahmedabad === undefined || rajkot === undefined) return [];
  const today = todayInIndia();
  const at = (days: number): string => `${shiftCalendarDay(today, -days)}T04:30:00.000Z`;
  const ref = (warehouse: WarehouseWire): MovementWire["warehouse"] => ({
    id: warehouse.id,
    code: warehouse.code,
    name: warehouse.name,
  });
  const stocked = products.filter((product) => product.is_active).slice(0, 12);
  const rows: MovementWire[] = [];
  let index = 0;
  const add = (
    warehouse: WarehouseWire,
    product: MockProductRecord,
    qty: number,
    kind: "receipt" | "adjustment",
    reference: string,
    note: string | null,
    days: number,
  ): void => {
    index += 1;
    rows.push({
      id: mockStockId(2, index),
      warehouse: ref(warehouse),
      product: { id: product.id, code: product.item_code, name: product.description },
      qty: String(qty),
      kind,
      reference,
      note,
      dispatch_no: null,
      order: null,
      created_by: KEEPER,
      created_at: at(days),
    });
  };
  stocked.forEach((product, position) => {
    const base = 400 + position * 150;
    add(ahmedabad, product, base, "receipt", "Opening", "Counted on 1 October.", 20);
    add(rajkot, product, Math.round(base / 10), "receipt", "Opening", null, 20);
  });
  const [first, second] = stocked;
  if (first !== undefined)
    add(ahmedabad, first, 500, "receipt", "GRN 2231", "From the Vadodara plant", 6);
  if (second !== undefined) add(ahmedabad, second, -25, "adjustment", "Damaged in rain", null, 3);
  // Newest first, as the ledger answers.
  return rows.reverse();
}
