import { z } from "zod";

/**
 * The backend's list metadata (`PageMeta` in its OpenAPI): keyset paging with an opaque
 * cursor, and an optional total.
 *
 * - `next_cursor` goes back as `?cursor=` for the next page; it is absent on the last page.
 * - `total` is only counted when the request asks for it (`?include_total=true`).
 * - `total_capped` means the count stopped at a ceiling: show "1,000+", not "1,000".
 */
export const pageMetaSchema = z
  .object({
    limit: z.number().int().positive(),
    next_cursor: z.string().min(1).nullish(),
    total: z.number().int().nonnegative().nullish(),
    total_capped: z.boolean().optional(),
  })
  .transform((meta) => ({
    limit: meta.limit,
    nextCursor: meta.next_cursor ?? null,
    total: meta.total ?? null,
    totalCapped: meta.total_capped ?? false,
  }));

/** One page of a cursor-paged list, as screens read it. */
export interface CursorPage<TItem> {
  readonly items: readonly TItem[];
  /** Pass back to load the next page; null on the last page. */
  readonly nextCursor: string | null;
  /** Rows matching across all pages, when the request asked for a count. */
  readonly total: number | null;
  /** The count stopped at a ceiling: there are at least `total` rows. */
  readonly totalCapped: boolean;
}
