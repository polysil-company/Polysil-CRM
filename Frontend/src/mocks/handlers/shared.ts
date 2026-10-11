import { HttpResponse } from "msw";

import { todayInIndia } from "@/lib/format";

/** The backend's error envelope: `{ error: { code, message, fields? } }`. */
export function errorResponse(
  status: number,
  code: string,
  message: string,
  fields?: Record<string, string>,
): Response {
  return HttpResponse.json(
    { error: { code, message, ...(fields === undefined ? {} : { fields }) } },
    { status },
  );
}

/** The mock's cursor is an offset, base64url-encoded like the backend's opaque cursors. */
export function encodeCursor(offset: number): string {
  return btoa(`offset:${String(offset)}`)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

/** The offset in a cursor, or null for one the mock did not write. */
export function decodeCursor(cursor: string): number | null {
  try {
    const match = /^offset:(\d+)$/.exec(atob(cursor.replace(/-/g, "+").replace(/_/g, "/")));
    return match?.[1] === undefined ? null : Number(match[1]);
  } catch {
    return null;
  }
}

/**
 * A stand-in for an export's workbook: one tab-separated line per row under the real file's
 * headers, named as the backend names it (`orders-2026-10-04.xlsx`).
 */
export function mockWorkbook(
  name: string,
  headers: readonly string[],
  rows: readonly (readonly string[])[],
): Response {
  const lines = [headers.join("\t"), ...rows.map((row) => row.join("\t"))];
  return new HttpResponse(lines.join("\n"), {
    headers: {
      "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "content-disposition": `attachment; filename="${name}-${todayInIndia()}.xlsx"`,
    },
  });
}
