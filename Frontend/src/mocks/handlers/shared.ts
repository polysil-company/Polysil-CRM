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

/** A file part of a multipart body, as the mock reads it. */
export interface MockUploadedFile {
  readonly name: string;
  readonly type: string;
  readonly size: number;
  readonly bytes: Uint8Array;
}

/**
 * The fields and files of a multipart request. Read by hand from the bytes, because a jsdom
 * test's `File` is not the one Node's own `request.formData()` accepts; a browser sends the
 * same bytes, so this reads both.
 */
export async function readMultipart(
  request: Request,
): Promise<Map<string, string | MockUploadedFile>> {
  const parts = new Map<string, string | MockUploadedFile>();
  const boundary = /boundary=(?:"([^"]+)"|([^;]+))/.exec(request.headers.get("content-type") ?? "");
  const marker = boundary?.[1] ?? boundary?.[2];
  if (marker === undefined) return parts;
  const bytes = new Uint8Array(await request.arrayBuffer());
  // One character per byte, so offsets in the text are offsets in the bytes.
  let text = "";
  for (const byte of bytes) text += String.fromCharCode(byte);
  const delimiter = `--${marker}`;
  let start = text.indexOf(delimiter);
  while (start !== -1) {
    const next = text.indexOf(delimiter, start + delimiter.length);
    if (next === -1) break;
    const part = text.slice(start + delimiter.length + 2, next - 2);
    const split = part.indexOf("\r\n\r\n");
    if (split !== -1) {
      const head = part.slice(0, split);
      const name = /name="([^"]*)"/.exec(head)?.[1];
      const filename = /filename="([^"]*)"/.exec(head)?.[1];
      const type = /content-type:\s*([^\r\n]+)/i.exec(head)?.[1] ?? "application/octet-stream";
      const bodyStart = start + delimiter.length + 2 + split + 4;
      const bodyEnd = next - 2;
      if (name !== undefined) {
        if (filename === undefined) {
          parts.set(name, new TextDecoder().decode(bytes.slice(bodyStart, bodyEnd)));
        } else {
          const content = bytes.slice(bodyStart, bodyEnd);
          parts.set(name, { name: filename, type, size: content.length, bytes: content });
        }
      }
    }
    start = next;
  }
  return parts;
}
