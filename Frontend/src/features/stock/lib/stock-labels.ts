import type { BadgeVariant } from "@/components/ui/badge";
import type { MovementKind, RecordableKind } from "@/features/stock/api/stock.schemas";
import { formatNumber } from "@/lib/format";

export const MOVEMENT_KIND_LABELS: Readonly<Record<MovementKind, string>> = {
  receipt: "Received",
  adjustment: "Correction",
  dispatch: "Dispatched",
  dispatch_void: "Dispatch undone",
};

export const MOVEMENT_KIND_BADGE: Readonly<Record<MovementKind, BadgeVariant>> = {
  receipt: "success",
  adjustment: "warning",
  dispatch: "info",
  dispatch_void: "neutral",
};

export const RECORDABLE_KIND_LABELS: Readonly<Record<RecordableKind, string>> = {
  receipt: "Stock received",
  adjustment: "A correction",
};

/** "1,250 m"; a decimal quantity keeps its decimals. */
export function quantityText(value: string, uom?: string | null): string {
  const number = Number(value);
  const decimals = Number.isInteger(number)
    ? 0
    : (value.split(".")[1]?.replace(/0+$/, "").length ?? 0);
  const text = formatNumber(number, Math.min(3, decimals));
  return uom ? `${text} ${uom}` : text;
}

/** A signed quantity for the ledger: "+250", "−25". */
export function signedQuantity(value: string): string {
  const number = Number(value);
  const magnitude = quantityText(String(Math.abs(number)));
  return number < 0 ? `−${magnitude}` : `+${magnitude}`;
}

export function isNegative(value: string): boolean {
  return Number(value) < 0;
}
