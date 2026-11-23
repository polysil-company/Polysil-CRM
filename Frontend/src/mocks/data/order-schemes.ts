import type { OrderSchemePreviewWire, OrderWire } from "@/features/orders/api/orders.schemas";
import type { EntitlementWire, SchemeWire } from "@/features/schemes/api/schemes.schemas";
import { todayInIndia } from "@/lib/format";

/**
 * SCHM-005 · The mock's scheme rules for an order (`schemes-contract.md`, FS-031). A sketch of
 * the backend's, enough to show every part of the screen; the backend's own rules decide.
 *
 * - Only an order through a channel partner gets scheme benefits; a scheme's partner and
 *   partner-type targets must match it. Every mock partner is in Gujarat, so territories match.
 * - Product targets narrow the counted lines; `basis` is their taxable value.
 * - Of the schemes that don't stack, only the largest discount counts; stackable ones add.
 * - The partner's available credits are used, up to what is left to pay.
 */

type SchemeRefWire = { id: string; code: string; name: string };

function paise(value: string): number {
  return Math.round(Number(value) * 100);
}

function rupees(value: number): string {
  return (value / 100).toFixed(2);
}

function refOf(scheme: SchemeWire): SchemeRefWire {
  return { id: scheme.id, code: scheme.code, name: scheme.name };
}

function runningToday(scheme: SchemeWire, today: string): boolean {
  return (
    scheme.is_active &&
    scheme.valid_from <= today &&
    (scheme.valid_to === null || scheme.valid_to === undefined || scheme.valid_to >= today)
  );
}

function aimedAtOrder(scheme: SchemeWire, order: OrderWire): boolean {
  const partner = order.partner;
  if (partner === null) return false;
  const match = (kind: "partner_type" | "partner", value: string | null | undefined): boolean => {
    const ids = scheme.targets.filter((target) => target.type === kind).map((target) => target.id);
    return ids.length === 0 || (value != null && ids.includes(value));
  };
  return match("partner_type", partner.partner_type) && match("partner", partner.id);
}

/** The lines a scheme counts, their taxable value and quantity. */
function counted(scheme: SchemeWire, order: OrderWire): { basis: number; qty: number } {
  const products = scheme.targets
    .filter((target) => target.type === "product")
    .map((target) => target.id);
  const lines =
    products.length === 0
      ? order.lines
      : order.lines.filter((line) => products.includes(line.product_id));
  return {
    basis: lines.reduce((sum, line) => sum + paise(line.taxable), 0),
    qty: lines.reduce((sum, line) => sum + Number(line.qty), 0),
  };
}

function qualifies(scheme: SchemeWire, order: OrderWire): { basis: number } | null {
  const { basis, qty } = counted(scheme, order);
  const measured = scheme.condition.metric === "order_value" ? basis / 100 : qty;
  const min = Number(scheme.condition.min);
  const max = scheme.condition.max == null ? null : Number(scheme.condition.max);
  if (basis <= 0 || measured < min || (max !== null && measured > max)) return null;
  return { basis };
}

function worth(benefit: SchemeWire["benefit"], basis: number): number {
  const raw =
    benefit.kind === "pct"
      ? Math.round((basis * Number(benefit.value)) / 100)
      : paise(benefit.value);
  return benefit.cap == null ? raw : Math.min(raw, paise(benefit.cap));
}

/** What submit would apply now, and what delivery would earn (GET /orders/{id}/schemes). */
export function previewOrderSchemes(
  order: OrderWire,
  schemes: readonly SchemeWire[],
  credits: readonly EntitlementWire[],
  now: Date = new Date(),
): OrderSchemePreviewWire {
  const today = todayInIndia(now);
  const eligible = schemes
    .filter((scheme) => runningToday(scheme, today) && aimedAtOrder(scheme, order))
    .flatMap((scheme) => {
      const met = qualifies(scheme, order);
      return met === null ? [] : [{ scheme, basis: met.basis }];
    });

  const discounts = eligible
    .filter(({ scheme }) => scheme.scheme_type === "order_discount")
    .map(({ scheme, basis }) => ({ scheme, basis, amount: worth(scheme.benefit, basis) }));
  const [bestSingle] = discounts
    .filter(({ scheme }) => !scheme.stackable)
    .sort((left, right) => right.amount - left.amount);
  const applied = [
    ...(bestSingle === undefined ? [] : [bestSingle]),
    ...discounts.filter(({ scheme }) => scheme.stackable),
  ];

  const total = paise(order.totals.total);
  let left = Math.max(0, total - applied.reduce((sum, item) => sum + item.amount, 0));
  const taxable = paise(order.totals.taxable);
  const used = credits
    .filter(
      (credit) =>
        credit.status === "available" &&
        credit.partner.id === order.partner?.id &&
        credit.expires_at.slice(0, 10) >= today,
    )
    .flatMap((credit) => {
      const value =
        credit.kind === "pct"
          ? Math.min(
              Math.round((taxable * Number(credit.value)) / 100),
              credit.cap == null ? Number.POSITIVE_INFINITY : paise(credit.cap),
            )
          : paise(credit.value);
      const amount = Math.min(value, left);
      left -= amount;
      return amount <= 0 ? [] : [{ credit, amount }];
    });

  const onDelivery = eligible
    .filter(({ scheme }) => ["order_points", "next_order"].includes(scheme.scheme_type))
    .map(({ scheme, basis }) => ({
      scheme: refOf(scheme),
      kind:
        scheme.scheme_type === "order_points"
          ? ("points" as const)
          : ("next_order_credit" as const),
      points:
        scheme.scheme_type === "order_points" ? Math.round(Number(scheme.benefit.value)) : null,
      basis: rupees(basis),
    }));

  const totalBenefit =
    applied.reduce((sum, item) => sum + item.amount, 0) +
    used.reduce((sum, item) => sum + item.amount, 0);
  return {
    discounts: applied.map(({ scheme, basis, amount }) => ({
      scheme: refOf(scheme),
      basis: rupees(basis),
      amount: rupees(amount),
    })),
    entitlements: used.map(({ credit, amount }) => ({
      entitlement_id: credit.id,
      scheme: credit.scheme,
      amount: rupees(amount),
    })),
    on_delivery: onDelivery,
    total_benefit: rupees(totalBenefit),
    payable: rupees(Math.max(0, total - totalBenefit)),
  };
}

/** What the order owes before benefits: the farmer's share on a subsidised order, else the total. */
function owedBeforeBenefits(order: OrderWire): number {
  return order.subsidy == null
    ? paise(order.totals.total)
    : Math.min(paise(order.totals.total), paise(order.subsidy.farmer_payable));
}

function appliedSum(order: OrderWire): number {
  return (order.benefits ?? [])
    .filter((benefit) => benefit.status === "applied")
    .reduce((sum, benefit) => sum + paise(benefit.amount), 0);
}

/** Submit stores the preview's figures as benefits, uses the credits, and lowers `payable`. */
export function applyOrderBenefits(
  order: OrderWire,
  preview: OrderSchemePreviewWire,
  credits: EntitlementWire[],
  newId: (index: number) => string,
  now: Date = new Date(),
): void {
  const at = now.toISOString();
  const earlier = order.benefits ?? [];
  const fresh = [
    ...preview.discounts.map((discount) => ({
      kind: "discount" as const,
      scheme: discount.scheme,
      amount: discount.amount,
    })),
    ...preview.entitlements.map((credit) => ({
      kind: "entitlement_used" as const,
      scheme: credit.scheme,
      amount: credit.amount,
    })),
  ].map((benefit, index) => ({
    id: newId(earlier.length + index),
    ...benefit,
    status: "applied" as const,
    applied_at: at,
  }));
  order.benefits = [...earlier, ...fresh];
  const ref = { id: order.id, order_no: order.order_no };
  for (const used of preview.entitlements) {
    const credit = credits.find((item) => item.id === used.entitlement_id);
    if (credit !== undefined) {
      credit.status = "consumed";
      credit.consumed_order = ref;
    }
  }
  order.payable = rupees(Math.max(0, owedBeforeBenefits(order) - appliedSum(order)));
}

/** Back to draft or cancelled: every applied benefit is reversed and its credit freed. */
export function reverseOrderBenefits(order: OrderWire, credits: EntitlementWire[]): void {
  const benefits = order.benefits ?? [];
  if (!benefits.some((benefit) => benefit.status === "applied")) return;
  order.benefits = benefits.map((benefit) =>
    benefit.status === "applied" ? { ...benefit, status: "reversed" as const } : benefit,
  );
  for (const credit of credits) {
    if (credit.status === "consumed" && credit.consumed_order?.id === order.id) {
      credit.status = "available";
      credit.consumed_order = null;
    }
  }
  order.payable =
    order.status === "cancelled" ? "0.00" : rupees(owedBeforeBenefits(order) - appliedSum(order));
}
