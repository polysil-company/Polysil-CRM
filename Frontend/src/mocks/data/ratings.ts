import type { ComplaintWire } from "@/features/complaints/api/complaints.schemas";
import type { OrderWire } from "@/features/orders/api/orders.schemas";
import type { RatingWire } from "@/features/ratings/api/ratings.schemas";

import { mockUuid } from "./reference";

/** The mock's own id space for ratings. */
export const RATING_SPACE = 0x5a7e;

/** Orders that have sent something: an installation can be rated from then. */
export const SHIPPED_ORDER_STATUSES: readonly string[] = [
  "partially_dispatched",
  "dispatched",
  "closed_short",
];

const ENTERED_BY = { id: "usr-001", full_name: "Asha Patel" };

/** The order's side of a rating, as the backend joins it. */
export function ratingOnOrder(order: OrderWire): Pick<RatingWire, "partner" | "lead" | "order"> {
  return {
    partner:
      order.partner === null
        ? null
        : {
            id: order.partner.id,
            name: order.partner.name,
            partner_type: order.partner.partner_type ?? "dealer",
          },
    lead: order.lead === null ? null : { id: order.lead.id, inquiry_no: order.lead.inquiry_no },
    order: { id: order.id, number: order.order_no, status: order.status },
  };
}

/** What a rating needs of a complaint. */
type RatedComplaint = Pick<ComplaintWire, "id" | "complaint_no" | "status" | "partner" | "lead">;

/** The complaint's side of a rating. */
export function ratingOnComplaint(
  complaint: RatedComplaint,
): Pick<RatingWire, "partner" | "lead" | "complaint"> {
  return {
    partner:
      complaint.partner == null || complaint.partner.name == null
        ? null
        : {
            id: complaint.partner.id,
            name: complaint.partner.name,
            partner_type: complaint.partner.partner_type ?? "dealer",
          },
    lead:
      complaint.lead == null
        ? null
        : { id: complaint.lead.id, inquiry_no: complaint.lead.inquiry_no ?? null },
    complaint: { id: complaint.id, number: complaint.complaint_no, status: complaint.status },
  };
}

/**
 * RATE-001 · A few ratings to start from: farmers' ratings of the first shipped orders (one
 * unhappy), a product on one of them, a dealer's own rating, and a closed complaint's service.
 * The second shipped order is left unrated so its buttons show.
 */
export function seedRatings(
  orders: readonly OrderWire[],
  complaints: readonly RatedComplaint[],
): RatingWire[] {
  const shipped = orders.filter((order) => SHIPPED_ORDER_STATUSES.includes(order.status));
  const ratings: RatingWire[] = [];
  const base = (index: number, daysAgo: number): Pick<RatingWire, "id" | "created_at"> => ({
    id: mockUuid(RATING_SPACE, index),
    created_at: new Date(Date.now() - daysAgo * 86_400_000).toISOString(),
  });
  const rated = [shipped[0], shipped[2], shipped[3]];
  const scores = [4, 2, 5];
  const comments = [
    "Drippers clogged in week two, cleared on the visit.",
    "The laterals arrived late and the fitting took three days.",
    null,
  ];
  rated.forEach((order, index) => {
    if (order === undefined) return;
    ratings.push({
      ...base(index + 1, 10 - index * 3),
      target: "installation",
      score: scores[index] ?? 4,
      comment: comments[index] ?? null,
      rated_by: "customer",
      entered_by: ENTERED_BY,
      entered_via: "staff",
      ...ratingOnOrder(order),
      complaint: null,
      product: null,
    });
  });
  const first = shipped[0];
  const line = first?.lines.find((item) => Number(item.qty_dispatched) > 0);
  if (first !== undefined && line !== undefined) {
    ratings.push({
      ...base(4, 6),
      target: "product",
      score: 3,
      comment: "Good pipe, but two joints leaked.",
      rated_by: "customer",
      entered_by: ENTERED_BY,
      entered_via: "staff",
      ...ratingOnOrder(first),
      complaint: null,
      product: { id: line.product_id, description: line.description },
    });
  }
  const dealerOrder = shipped.find((order) => order.partner !== null);
  if (dealerOrder !== undefined) {
    ratings.push({
      ...base(5, 4),
      target: "installation",
      score: 4,
      comment: "Delivery on time this season.",
      rated_by: "dealer",
      entered_by: { id: "usr-102", full_name: "Bhavesh Shah" },
      entered_via: "dealer",
      ...ratingOnOrder(dealerOrder),
      complaint: null,
      product: null,
    });
  }
  const closed = complaints.find((complaint) => complaint.status === "closed");
  if (closed !== undefined) {
    ratings.push({
      ...base(6, 2),
      target: "service",
      score: 1,
      comment: "Nobody came for a week after the complaint.",
      rated_by: "customer",
      entered_by: ENTERED_BY,
      entered_via: "staff",
      ...ratingOnComplaint(closed),
      order: null,
      product: null,
    });
  }
  return ratings.sort((left, right) => right.created_at.localeCompare(left.created_at));
}
