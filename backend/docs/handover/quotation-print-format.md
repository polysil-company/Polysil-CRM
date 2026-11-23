# The quotation's print format and the company profile

No endpoint changed. No request or response shape changed. Only the PDF did.

## What changed

The quotation PDF is now laid out like the client's own sheet, and the client's company profile follows it in the same file.

| | Before | Now |
|---|---|---|
| First page | landscape A4, up to nineteen columns | portrait A4, seven columns |
| Pages | one or two | the quotation's pages, then seven landscape pages of company profile |
| Size | about 40 KB | about 0.9 MB |
| Title | `Quotation <no> v<n>` | the same |

The order PDF is unchanged.

## What to check on your side

1. **The PDF viewer on the quotation detail screen.** `GET /quotations/{id}/pdf` returns the same link envelope. The file behind it now mixes portrait and landscape pages. Do not assume one orientation or one page.
2. **The public quotation page.** `GET /public/q/{token}/pdf` still answers 302 to the file. It is larger now, so show progress on a slow phone.
3. **Nothing else.** The preview, the line editor and the totals on screen read the same fields as before.

## What prints, so the screen can match it

The page shows one discount column, not three. If the detail screen wants to mirror the PDF:

| On the PDF | From the API |
|---|---|
| Price | line `rate` |
| Price after Dis. | line `taxable` / `qty`, rounded half up to two decimals; the `rate` when the line's `discount` is 0 |
| Qty. | `qty` with `uom` |
| Discount. Amt. | line `discount` |
| Total Amt. | line `taxable` |
| Sub Total, CGST, SGST or IGST, Total | `taxable`, `cgst`, `sgst`, `igst`, `total` |
| Total Discount Amt. | `discount` |

The screen may keep its three discount columns. This is only what the customer sees on paper.

## Not printed

The approver's name. A dealer never learns who approved, on screen or on paper.

## Old quotations

A quotation sent before this change keeps its old PDF. Only new sends and sent revisions get the new layout.
