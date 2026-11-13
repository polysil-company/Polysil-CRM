---
date: 2026-10-18
type: feature
title: Ratings and the dealer rating
dataIds:
  - RATE-001
  - RATE-002
  - RATE-003
  - RATE-004
author: Nakul Srivastava
breaking: false
---

## Before

Nothing recorded what a farmer or a dealer thought of an installation, a product or a service visit. Nothing showed how well a dealer pays or how much it orders.

## Now

Built to `ratings-contract.md` (FS-043) and the generated `ratings.md`. Ratings get a new Data ID domain, `RATE`.

**Rating something** (RATE-001)

- A **Ratings** card on the order, beside Warranty, once something has shipped:
  - **Rate installation** in its header;
  - **Rate a product shipped**, with **Rate** on each product sent.
- The same card on a closed complaint, with **Rate service**.
- The form asks for 1 to 5 stars, with words for each ("4 stars: Good"), and an optional comment of up to 1,000 characters.
  - Staff record what the farmer said; it needs orders edit (complaints edit for a service).
  - A dealer's user rates for its firm, on its own orders and complaints.
  - The form says a rating is never changed.
- Each button goes once this kind of rater has rated it.
- These refusals show in the form, in words: `not_rateable`, `product_not_shipped`, `rating_exists`, `not_your_order`.

**Reading them** (RATE-002)

- The card lists each rating: who rated it and what, the stars with their word, the comment, and who entered it.
- A dealer sees a customer's rating as the score only ("Customer rating", stars, "2 stars").
- **Ratings** under Service (`/ratings`, staff who see orders) lists every rating newest first, each linked to its order or complaint and naming the dealer. It filters by kind, and **1 or 2 stars** shows the unhappy customers.
- Loading, empty ("No unhappy customers"), error with a retry, and **Show more**.

**Summary** (RATE-003)

- The page's **Summary** tab groups ratings **by dealer**, **by product** or **by kind**. Each row has the average with stars, the count, and the 1 or 2 star ratings in red. The lowest average comes first.

**The dealer rating** (RATE-004)

- On a channel partner's page for staff, and as **Your rating** above a partner user's own ledger. It is hidden on a 403 (`rating_not_permitted`).
- It shows:
  - the rating out of 5, with stars;
  - days to full payment, and order value before GST, each scored "n of 5";
  - how many orders were counted and paid in full;
  - customers' feedback, shown apart.
- With no order counted, or none paid in full, it says **Not rated yet** and why.
- The footnote: "From days to full payment and order value over the last year. Feedback is shown apart."
- The three settings it uses were already editable in Company settings (the `bands` kind).

**A new pattern and token**

- `StarRating` shows a score as stars, read out as "4 out of 5 stars".
- `StarRatingInput` uses native radio buttons in a fieldset, so arrow keys move between stars. Each star is a 44 px target, and each reads "4 stars, Good".
- A `rating` colour token, in `tokens.css` and the design system doc, for filled stars: gold in light and dark mode. The warning colour read brown on white.

**Mock**

- Seeded ratings: farmers' ratings of shipped orders (one of 2 stars), a product, a dealer's own rating, and a 1-star service on a closed complaint.
- Every rule above, including the score-only view for dealers.
- The dealer rating is worked out from the mock's orders and payments with the settings' bands.

Walked as Admin on a desktop in light mode and a 390 px phone in dark mode: rating an installation, the order and complaint cards, the page with its low filter and summary, and the dealer card. Axe found nothing, with no console errors and no sideways scroll.

## Discussion

- **The Ratings page is staff-only and gated on orders view.** Ratings are read through the order's or complaint's own permission, and there is no ratings module. A dealer reads its ratings on its own orders and complaints.
- **The dealer card shows for every partner.** The backend works it out for any partner id, so the frontend doesn't decide which partner types have one.
- **A rating is never edited.** The contract has no edit or delete, so the form says so before saving.
- **This is part 34a.** The consumer portal (farmers signing in) follows in 34b.

## Files changed

- `src/features/ratings/`: new.
  - `api/ratings.schemas.ts`, `.api.ts`, `.queries.ts`, `.mutations.ts`: the contract, the four calls, the list, summary and dealer queries, and the create mutation.
  - `lib/rating-labels.ts`: labels, words for each score, and the refusals.
  - `components/rating-form.tsx`: the form.
  - `components/record-ratings.tsx`: the card on an order or complaint, and `RatingRow`.
  - `components/ratings-page.tsx`, `hooks/use-ratings-params.ts`: the page and its URL state.
  - `components/dealer-rating.tsx`: the dealer card.
- `src/components/patterns/star-rating.tsx`, `.stories.tsx`: new, `StarRating` and `StarRatingInput`.
- `src/styles/tokens.css`, `Docs/Design-System.md`: the `rating` colour.
- `src/app/(app)/ratings/page.tsx`: new route; `src/components/layout/navigation.ts`: the Ratings item.
- `src/features/orders/components/order-detail.tsx`, `src/features/complaints/components/complaint-detail.tsx`: the Ratings card.
- `src/features/partners/components/partner-detail.tsx`, `src/features/payments/components/my-ledger.tsx`: the dealer card.
- Mock: `src/mocks/data/ratings.ts`, `src/mocks/handlers/ratings.ts` (new), `src/mocks/db.ts`, `src/mocks/handlers/index.ts`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: the `RATE` domain and RATE-001…004.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/ratings/`.

## Tests

`src/features/ratings/components/ratings.test.tsx`, 9 tests:

- `[RATE-002] Ratings list (contract)`: newest first, the low ones, and a dealer's score-only view.
- `[RATE-001] Recording a rating (contract)`:
  - once per kind, then `rating_exists`, `not_rateable` (unshipped, open complaint) and `product_not_shipped`;
  - orders edit for staff, and `not_your_order` for a dealer.
- `[RATE-003] Ratings summary (contract)`: by kind and by dealer, lowest first.
- `[RATE-004] Dealer rating (contract)`: Admin and the dealer itself read it; a QA manager gets `rating_not_permitted`.
- `[RATE-001] RecordRatingsCard`:
  - stars required, then the installation rated and its button gone;
  - a closed complaint's service rating.
- `[RATE-002] RatingsPage`: 1 or 2 stars narrows the list, and the summary by kind.
- `[RATE-004] DealerRatingCard`: shown to Admin, hidden from a QA manager.

To check by hand in the mock as Admin:

1. Open a dispatched order → Ratings → **Rate installation**, then rate a product.
2. Open Service → **Ratings**, choose **1 or 2 stars**, then **Summary**.
3. Open a channel partner with orders and read its **Dealer rating**.
