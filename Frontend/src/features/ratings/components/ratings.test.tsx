import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { getComplaint } from "@/features/complaints/api/complaints.api";
import { getOrder } from "@/features/orders/api/orders.api";
import type { OrderWire } from "@/features/orders/api/orders.schemas";
import {
  createRating,
  getDealerRating,
  getRatingSummary,
  listRatings,
} from "@/features/ratings/api/ratings.api";
import type { RatingListParams } from "@/features/ratings/api/ratings.schemas";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { SHIPPED_ORDER_STATUSES } from "@/mocks/data/ratings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { DealerRatingCard } from "./dealer-rating";
import { RatingsPage } from "./ratings-page";
import { RecordRatingsCard } from "./record-ratings";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

let keys = 0;
function key(): string {
  keys += 1;
  return `rating-${String(keys)}`;
}

async function codeOf(call: Promise<unknown>): Promise<string | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? (error.code ?? null) : null;
}

const ALL: RatingListParams = {
  target: null,
  salesOrderId: null,
  complaintId: null,
  partnerId: null,
  maxScore: null,
};

/** The second shipped order: the seed leaves it unrated. */
function unratedShippedOrder(): OrderWire {
  const order = mockDb.orders.filter((item) => SHIPPED_ORDER_STATUSES.includes(item.status))[1];
  if (order === undefined) throw new Error("No second shipped order");
  return order;
}

function unshippedOrder(): OrderWire {
  const order = mockDb.orders.find((item) =>
    item.lines.every((line) => Number(line.qty_dispatched) === 0),
  );
  if (order === undefined) throw new Error("No unshipped order");
  return order;
}

describe("[RATE-002] Ratings list (contract)", () => {
  afterEach(reset);

  it("lists newest first, keeps the low ones apart, and shows a dealer the score only", async () => {
    reset();
    const page = await listRatings({ ...ALL, cursor: null });
    expect(page.items.length).toBeGreaterThan(3);
    const dates = page.items.map((rating) => rating.createdAt);
    expect(dates).toEqual([...dates].sort((left, right) => right.localeCompare(left)));
    const low = await listRatings({ ...ALL, maxScore: 2, cursor: null });
    expect(low.items.length).toBeGreaterThan(0);
    expect(low.items.every((rating) => rating.score <= 2)).toBe(true);

    const customer = mockDb.ratings.find(
      (rating) => rating.rated_by === "customer" && rating.comment !== null,
    );
    const partner = mockMeFor("dealer").data.partner;
    if (customer === undefined || partner == null) throw new Error("No seeded rating");
    customer.partner = { id: partner.id, name: partner.name ?? "", partner_type: "dealer" };
    writeMockRole("dealer");
    const seen = (await listRatings({ ...ALL, cursor: null })).items.find(
      (rating) => rating.id === customer.id,
    );
    expect(seen).toMatchObject({ comment: null, enteredBy: null, score: customer.score });
  });
});

describe("[RATE-001] Recording a rating (contract)", () => {
  afterEach(reset);

  it("rates a shipped order once, and refuses what can't be rated", async () => {
    reset();
    const order = unratedShippedOrder();
    const saved = await createRating({
      body: { target: "installation", sales_order_id: order.id, score: 5, comment: "  Neat  " },
      idempotencyKey: key(),
    });
    expect(saved).toMatchObject({ target: "installation", ratedBy: "customer", comment: "Neat" });
    expect(
      await codeOf(
        createRating({
          body: { target: "installation", sales_order_id: order.id, score: 3 },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("rating_exists");
    expect(
      await codeOf(
        createRating({
          body: { target: "installation", sales_order_id: unshippedOrder().id, score: 3 },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("not_rateable");
    expect(
      await codeOf(
        createRating({
          body: {
            target: "product",
            sales_order_id: order.id,
            product_id: "not-on-this-order",
            score: 3,
          },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("product_not_shipped");
    const open = mockDb.complaints.find((complaint) => complaint.status !== "closed");
    expect(
      await codeOf(
        createRating({
          body: { target: "service", complaint_id: open?.id ?? "", score: 3 },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("not_rateable");
  });

  it("needs orders edit from staff, and a dealer's own order from a dealer", async () => {
    reset();
    const order = unratedShippedOrder();
    writeMockRole("account_manager");
    expect(
      await codeOf(
        createRating({
          body: { target: "installation", sales_order_id: order.id, score: 4 },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("forbidden");
    writeMockRole("dealer");
    order.partner = { id: "prt-other", name: "Another Dealer", partner_type: "dealer" };
    expect(
      await codeOf(
        createRating({
          body: { target: "installation", sales_order_id: order.id, score: 4 },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("not_your_order");
  });
});

describe("[RATE-003] Ratings summary (contract)", () => {
  afterEach(reset);

  it("groups by dealer and by kind, lowest average first", async () => {
    reset();
    const byKind = await getRatingSummary("target");
    expect(byKind.map((row) => row.key.id).sort()).toEqual(["installation", "product", "service"]);
    const averages = byKind.map((row) => row.average);
    expect(averages).toEqual([...averages].sort((left, right) => left - right));
    expect(byKind.find((row) => row.key.id === "service")?.low).toBe(1);
    expect((await getRatingSummary("partner")).length).toBeGreaterThan(0);
  });
});

describe("[RATE-004] Dealer rating (contract)", () => {
  afterEach(reset);

  it("gives staff who see payments and the dealer itself the figures, and refuses others", async () => {
    reset();
    const partnerId = mockMeFor("dealer").data.partner?.id ?? "";
    const rating = await getDealerRating(partnerId);
    expect(rating).toMatchObject({ partnerId, windowDays: 365 });
    expect(rating.rating === null || (rating.rating >= 1 && rating.rating <= 5)).toBe(true);
    writeMockRole("dealer");
    expect((await getDealerRating(partnerId)).partnerId).toBe(partnerId);
    writeMockRole("qa_manager");
    expect(await codeOf(getDealerRating(partnerId))).toBe("rating_not_permitted");
  });
});

describe("[RATE-001] RecordRatingsCard", () => {
  afterEach(reset);

  it("rates the installation of a shipped order, asking for the stars first", async () => {
    reset();
    signInAs("admin");
    const order = await getOrder(unratedShippedOrder().id);
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <RecordRatingsCard kind="order" order={order} />
        <Toaster />
      </>,
    );
    expect(await screen.findByText("Not rated yet.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Products to rate" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rate installation" }));
    const form = await screen.findByRole("form", { name: "Rate the installation" });
    await user.click(within(form).getByRole("button", { name: "Save rating" }));
    expect(await within(form).findByText("Choose how many stars.")).toBeInTheDocument();
    await user.click(within(form).getByRole("radio", { name: "4 stars, Good" }));
    await user.type(within(form).getByLabelText(/Comment/), "Fitted in a day");
    await user.click(within(form).getByRole("button", { name: "Save rating" }));
    expect(await screen.findByText("Rating saved")).toBeInTheDocument();
    expect(await screen.findByText(/Fitted in a day/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Rate installation" })).not.toBeInTheDocument();
    });
  });

  it("shows a closed complaint's service rating, with no button once rated", async () => {
    reset();
    signInAs("admin");
    const closed = mockDb.complaints.find((complaint) => complaint.status === "closed");
    if (closed === undefined) throw new Error("No closed complaint");
    const complaint = await getComplaint(closed.id);
    renderWithProviders(<RecordRatingsCard kind="complaint" complaint={complaint} />);
    expect(await screen.findByText("Customer · Service")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "1 out of 5 stars" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rate service" })).not.toBeInTheDocument();
  });
});

describe("[RATE-002] RatingsPage", () => {
  afterEach(reset);

  it("lists ratings, narrows to 1 or 2 stars, and sums them up by kind", async () => {
    reset();
    signInAs("admin");
    const user = userEvent.setup();
    renderWithProviders(<RatingsPage />);
    const list = await screen.findByRole("list", { name: "Ratings, newest first" });
    const all = within(list).getAllByRole("listitem").length;
    await user.click(screen.getByRole("button", { name: "1 or 2 stars" }));
    await waitFor(() => {
      expect(
        within(screen.getByRole("list", { name: "Ratings, newest first" })).getAllByRole("listitem")
          .length,
      ).toBeLessThan(all);
    });
    await user.click(screen.getByRole("tab", { name: "Summary" }));
    await user.click(await screen.findByRole("button", { name: "By kind" }));
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("rowheader", { name: "Service" })).toBeInTheDocument();
  });
});

describe("[RATE-004] DealerRatingCard", () => {
  afterEach(reset);

  it("shows the rating to staff who see payments, and nothing to those who don't", async () => {
    reset();
    signInAs("admin");
    const partnerId = mockMeFor("dealer").data.partner?.id ?? "";
    const { unmount } = renderWithProviders(<DealerRatingCard partnerId={partnerId} />);
    expect(await screen.findByText("Days to full payment")).toBeInTheDocument();
    expect(screen.getByText(/Feedback is shown apart/)).toBeInTheDocument();
    unmount();
    signInAs("qa_manager");
    renderWithProviders(<DealerRatingCard partnerId={partnerId} />);
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Dealer rating" })).not.toBeInTheDocument();
    });
  });
});
