import { z } from "zod";

import { pageMetaSchema } from "@/lib/api/pagination";

/**
 * MSTR-014 … MSTR-016 · Stock (handover `stock-contract.md`, `docs/api/stock.md`): what each
 * warehouse holds, what open orders have committed, and what is left. Quantities are decimal
 * strings in the product's unit. Every staff role reads; Dispatch records; Admin keeps the
 * warehouses. Dealers see no stock.
 */

const id = z.string().min(1);
const quantity = z.string().regex(/^-?\d+(\.\d+)?$/);
const isoDateTime = z.iso.datetime({ offset: true });

const warehouseRefSchema = z.object({ id, code: z.string(), name: z.string() });
export type WarehouseRef = z.output<typeof warehouseRefSchema>;

const productRefSchema = z.object({ id, code: z.string().nullable(), name: z.string() });

// ── warehouses (MSTR-016) ────────────────────────────────────────────────────────

const warehouseWireSchema = z.object({
  id,
  code: z.string().min(1),
  name: z.string().min(1),
  territory_id: z.string().nullable(),
  is_default: z.boolean(),
  is_active: z.boolean(),
});
export type WarehouseWire = z.input<typeof warehouseWireSchema>;

export interface Warehouse {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly territoryId: string | null;
  readonly isDefault: boolean;
  readonly active: boolean;
}

function toWarehouse(wire: z.output<typeof warehouseWireSchema>): Warehouse {
  return {
    id: wire.id,
    code: wire.code,
    name: wire.name,
    territoryId: wire.territory_id,
    isDefault: wire.is_default,
    active: wire.is_active,
  };
}

export const warehouseListSchema = z
  .object({ data: z.array(warehouseWireSchema) })
  .transform(({ data }) => data.map(toWarehouse));

export const warehouseResponseSchema = z
  .object({ data: warehouseWireSchema })
  .transform(({ data }) => toWarehouse(data));

export interface WarehouseRequest {
  readonly code: string;
  readonly name: string;
  readonly territory_id: string | null;
  readonly is_default: boolean;
  readonly is_active: boolean;
}

// ── the stock list (MSTR-014) ────────────────────────────────────────────────────

const stockRowWireSchema = z.object({
  warehouse: warehouseRefSchema,
  product: productRefSchema,
  on_hand: quantity,
  /** What submitted, approved and partly dispatched orders for this warehouse still owe. */
  committed: quantity,
  /** On hand less committed. Negative is short. */
  available: quantity,
  uom: z.string(),
});
export type StockRowWire = z.input<typeof stockRowWireSchema>;

export interface StockRow {
  readonly warehouse: WarehouseRef;
  readonly product: { readonly id: string; readonly code: string | null; readonly name: string };
  readonly onHand: string;
  readonly committed: string;
  readonly available: string;
  readonly uom: string;
}

export const stockPageSchema = z
  .object({ data: z.array(stockRowWireSchema), meta: pageMetaSchema })
  .transform(({ data, meta }) => ({
    items: data.map((row): StockRow => ({
      warehouse: row.warehouse,
      product: row.product,
      onHand: row.on_hand,
      committed: row.committed,
      available: row.available,
      uom: row.uom,
    })),
    nextCursor: meta.nextCursor,
  }));
export type StockPage = z.output<typeof stockPageSchema>;

export interface StockListParams {
  readonly warehouseId: string | null;
  readonly productId: string | null;
  readonly shortOnly: boolean;
}

// ── movements (MSTR-014 ledger, MSTR-015 recording) ──────────────────────────────

export const MOVEMENT_KINDS = ["receipt", "adjustment", "dispatch", "dispatch_void"] as const;
export type MovementKind = (typeof MOVEMENT_KINDS)[number];

/** What a person records; dispatches move stock by themselves. */
export const RECORDABLE_KINDS = ["receipt", "adjustment"] as const;
export type RecordableKind = (typeof RECORDABLE_KINDS)[number];

const movementWireSchema = z.object({
  id,
  warehouse: warehouseRefSchema,
  product: productRefSchema,
  qty: quantity,
  kind: z.enum(MOVEMENT_KINDS),
  reference: z.string().nullable(),
  note: z.string().nullable(),
  /** Set for dispatch movements. */
  dispatch_no: z.string().nullable(),
  /** The order number, for dispatch movements. */
  order: z.string().nullable(),
  created_by: z.object({ id, full_name: z.string() }).nullable(),
  created_at: isoDateTime,
});
export type MovementWire = z.input<typeof movementWireSchema>;

export interface Movement {
  readonly id: string;
  readonly warehouse: WarehouseRef;
  readonly product: { readonly id: string; readonly code: string | null; readonly name: string };
  readonly qty: string;
  readonly kind: MovementKind;
  readonly reference: string | null;
  readonly note: string | null;
  readonly dispatchNo: string | null;
  readonly orderNo: string | null;
  readonly createdBy: string | null;
  readonly createdAt: string;
}

export const movementPageSchema = z
  .object({ data: z.array(movementWireSchema), meta: pageMetaSchema })
  .transform(({ data, meta }) => ({
    items: data.map((row): Movement => ({
      id: row.id,
      warehouse: row.warehouse,
      product: row.product,
      qty: row.qty,
      kind: row.kind,
      reference: row.reference,
      note: row.note,
      dispatchNo: row.dispatch_no,
      orderNo: row.order,
      createdBy: row.created_by?.full_name ?? null,
      createdAt: row.created_at,
    })),
    nextCursor: meta.nextCursor,
  }));
export type MovementPage = z.output<typeof movementPageSchema>;

export interface MovementListParams {
  readonly warehouseId: string | null;
  readonly productId: string | null;
}

export interface RecordStockRequest {
  readonly warehouse_id: string;
  readonly kind: RecordableKind;
  readonly reference: string | null;
  readonly note: string | null;
  readonly lines: readonly { readonly product_id: string; readonly qty: string }[];
}

export const recordedSchema = z
  .object({
    data: z.object({
      movements: z.array(z.object({ id, product_id: id, qty: quantity, on_hand_after: quantity })),
    }),
  })
  .transform(({ data }) =>
    data.movements.map((row) => ({
      id: row.id,
      productId: row.product_id,
      qty: row.qty,
      onHandAfter: row.on_hand_after,
    })),
  );
export type Recorded = z.output<typeof recordedSchema>;

// ── availability on the order form (DISP-003) ────────────────────────────────────

export const availabilitySchema = z
  .object({
    data: z.object({
      warehouse_id: id,
      items: z.array(z.object({ product_id: id, available: quantity, on_hand: quantity })),
    }),
  })
  .transform(({ data }) => ({
    warehouseId: data.warehouse_id,
    items: data.items.map((item) => ({
      productId: item.product_id,
      available: item.available,
      onHand: item.on_hand,
    })),
  }));
export type Availability = z.output<typeof availabilitySchema>;

/** `GET /stock/availability` takes at most this many products. */
export const MAX_AVAILABILITY_PRODUCTS = 100;
