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

/** The metadata as the backend writes it — for page wire types and the mock backend. */
export type PageMetaWire = z.input<typeof pageMetaSchema>;

/** One page of a cursor-paged list, as screens read it. */
export interface CursorPage<TItem> {
  readonly items: readonly TItem[];
  /** Pass back to load the next page; null on the last page. */
  readonly nextCursor: string | null;
  /** Rows matching across all pages, when the request asked for a count. */
  readonly total: number | null;
  /** The count stopped at a ceiling: there are at least `total` rows. */
  readonly totalCapped: boolean;
  /** Rows left out because they did not match the contract. Normally 0. */
  readonly skipped: number;
}

/** "stage: Invalid option; mobile: Too small" — enough to name what changed. */
function describeIssues(error: z.core.$ZodError): string {
  return error.issues
    .slice(0, 3)
    .map((issue) => `${issue.path.map(String).join(".") || "(root)"}: ${issue.message}`)
    .join("; ");
}

/**
 * `{ data: TItem[], meta: PageMeta }`, read one row at a time.
 *
 * A single row the backend sends wrong — a missing name, a code it stopped filling in —
 * would otherwise fail the whole page and replace two dozen good records with an error
 * screen. Such a row is left out instead and counted in `skipped`, which the calling
 * module logs. A page where EVERY row fails is still a contract violation: that is a
 * change of shape, not one bad record.
 */
export function cursorPageSchema<TItem extends z.ZodType>(
  itemSchema: TItem,
): z.ZodType<CursorPage<z.output<TItem>>, { data: unknown[]; meta: PageMetaWire }> {
  return z
    .object({ data: z.array(z.unknown()), meta: pageMetaSchema })
    .transform((page, ctx): CursorPage<z.output<TItem>> => {
      const items: z.output<TItem>[] = [];
      let firstFailure: string | undefined;

      for (const row of page.data) {
        const parsed = itemSchema.safeParse(row);
        if (parsed.success) {
          items.push(parsed.data);
        } else {
          firstFailure ??= describeIssues(parsed.error);
        }
      }

      const skipped = page.data.length - items.length;
      if (items.length === 0 && skipped > 0) {
        ctx.addIssue({
          code: "custom",
          path: ["data"],
          message: `no row of ${String(skipped)} matched the contract; the first one failed with ${firstFailure ?? "no issues"}`,
        });
        return z.NEVER;
      }

      return {
        items,
        nextCursor: page.meta.nextCursor,
        total: page.meta.total,
        totalCapped: page.meta.totalCapped,
        skipped,
      };
    });
}
