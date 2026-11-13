# Excel import with column matching

Full contract: `docs/api/imports.md`. New endpoints; nothing existing changes.

## What it is

An "Import from Excel" dialog in three places, one backend for all of them:

| Where | `kind` | Commit |
|---|---|---|
| Channel partners list | `partners` | creates the partners |
| A draft price list's rates tab | `price_list_items` (send `target_id`: the list) | writes the rates |
| Order and quotation line editors | `lines` | none: the check returns the lines, the form adds them |

Channel partners is now in the production menu (`channel-partners` in the release list).

**A partner import never creates a login.** Portal access is still the per-dealer "Create login" step (`POST /users`).

## The dialog

**Step 1: upload.** File picker for `.xlsx` or `.csv`, 10 MB at most.

```
POST /imports   (multipart, Idempotency-Key)
kind=partners, file=<file>, [target_id], [sheet], [header_row]
```

The answer has `headers`, `sample` (first five rows), `fields`, `suggested_mapping`, `sheets`, `sheet` and `header_row`. When `sheets` has more than one, show a sheet picker; changing it, or the header row, is a new upload with `sheet` or `header_row`.

**Step 2: match columns.** One row per column of their file: the header, two sample values, and a dropdown of `fields` (label, with `help` under it) plus "Skip". Pre-fill from `suggested_mapping` (field key to column index). Mark `required` fields. Price imports also show Replace / Merge.

```
POST /imports/{id}/check   (Idempotency-Key)
{ "mapping": { "name": 0, "mobile": 1, "code": 6 }, "options": { "mode": "replace" } }
```

A bad mapping is `422` with `fields["mapping.<key>"]`: show it on that dropdown.

**Step 3: review.** Show `total`, `ok`, `errors`; the `error_rows` table (sheet row, field label, reason); the `preview` rows; and any `column_warnings` beside their dropdown. Buttons:

- "Back to matching"
- "Import good rows only": commit with `skip_invalid: true`
- "Import": disabled while `errors > 0`

For `lines`, the button is "Add to order" (or quotation): put `check.lines` into the line editor and close. Each line has `product_id`, `product`, `qty` and three discounts. The usual preview and save then price them.

```
POST /imports/{id}/commit   (Idempotency-Key)
{ "skip_invalid": false }
→ { "status": "committed", "created": 209, "skipped": 3, "price_list_id": null }
```

**Done:** "209 partners created, 3 skipped." Refresh the list.

Closing the dialog without importing: `DELETE /imports/{id}`.

## Refusals

| Code | Say |
|---|---|
| `413 attachment_too_large` | "Files up to 10 MB." |
| `422 import_unreadable` | the message as given (it names the fix: save as .xlsx, and so on) |
| `422 import_too_many_rows` | the message as given |
| `422 import_has_errors` on commit | rows changed since the check; show `fields` (`rows[<row>].<field>`) and go back to step 3 |
| `409 import_wrong_state` | "This import is finished. Upload the file again." |
| `409 price_list_published` | "This list is published. Make a new draft to import into." |
| `403` | partner and price imports are staff only; hide the button for portal users |
