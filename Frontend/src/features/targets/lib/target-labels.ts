import type { TargetMetric } from "@/features/targets/api/targets.schemas";
import { formatInr, formatNumber } from "@/lib/format";

export const METRIC_LABELS: Readonly<Record<TargetMetric, string>> = {
  order_value: "Order value",
  orders: "Orders",
  leads_won: "Leads won",
  visits: "Visits",
};

/** A figure as the measure reads it: rupees for order value, a count for the others. */
export function formatMeasure(metric: TargetMetric, value: string | number): string {
  return metric === "order_value" ? formatInr(String(value)) : formatNumber(Number(value));
}

/** "63.6%" from the backend's "63.6". */
export function formatShare(pct: string): string {
  return `${formatNumber(Number(pct), 1)}%`;
}

export function isTargetMetric(value: string): value is TargetMetric {
  return (
    value === "order_value" || value === "orders" || value === "leads_won" || value === "visits"
  );
}
