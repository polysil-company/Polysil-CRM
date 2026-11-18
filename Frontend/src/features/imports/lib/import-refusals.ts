import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";

/**
 * MSTR-007 · An import refusal in words (handover `excel-import.md`, "Refusals"). The backend's
 * own message is shown where the handover says so: it names the fix ("save it as .xlsx").
 */
export interface ImportRefusal {
  /** Said above the buttons; null when everything lands on a dropdown or a row. */
  readonly message: string | null;
  /** `mapping.<key>` errors, by field key: shown on that field's dropdown. */
  readonly mapping: Readonly<Record<string, string>>;
  /** `rows[<row>].<field>` errors on a commit: the rows changed since the check. */
  readonly rows: readonly {
    readonly row: number;
    readonly field: string;
    readonly reason: string;
  }[];
  /** Nothing more can be done with this import: upload the file again. */
  readonly finished: boolean;
  /**
   * MSTR-013 · What the upload itself was refused on, shown under its own control: the file
   * (unreadable, a header with no rows under it), the sheet, or the column-names row.
   */
  readonly upload: {
    readonly file?: string;
    readonly sheet?: string;
    readonly headerRow?: string;
  };
}

const MAPPING_PATH = /^mapping\.(.+)$/;
const ROW_PATH = /^rows\[(\d+)\]\.(.+)$/;

const NO_FIELDS: ImportRefusal = {
  message: null,
  mapping: {},
  rows: [],
  finished: false,
  upload: {},
};

/** Where an upload refusal's `fields` key lands. */
const UPLOAD_FIELDS: Readonly<Record<string, keyof ImportRefusal["upload"]>> = {
  file: "file",
  sheet: "sheet",
  header_row: "headerRow",
};

export function importRefusal(error: unknown): ImportRefusal {
  if (!isApiError(error)) {
    return { ...NO_FIELDS, message: toUserFacingError(error).title };
  }
  if (error.status === 413 || error.code === "attachment_too_large") {
    return { ...NO_FIELDS, message: "Files up to 10 MB." };
  }
  switch (error.code) {
    case "import_unreadable":
    case "import_too_many_rows": {
      // The backend's own words name the fix ("save it as .xlsx"); they go under the file.
      const onFile = readFieldErrors(error)?.file;
      return { ...NO_FIELDS, upload: { file: onFile ?? error.message } };
    }
    case "import_wrong_state":
      return {
        ...NO_FIELDS,
        message: "This import is finished. Upload the file again.",
        finished: true,
      };
    case "price_list_published":
      return {
        ...NO_FIELDS,
        message: "This list is published. Make a new draft to import into.",
        finished: true,
      };
    default:
      break;
  }
  if (error.status === 403) {
    return { ...NO_FIELDS, message: "You may not import this.", finished: true };
  }
  const fields = readFieldErrors(error);
  if (fields !== null) {
    const mapping: Record<string, string> = {};
    const rows: { row: number; field: string; reason: string }[] = [];
    const rest: string[] = [];
    const upload: { file?: string; sheet?: string; headerRow?: string } = {};
    for (const [path, reason] of Object.entries(fields)) {
      const onMapping = MAPPING_PATH.exec(path);
      const onRow = ROW_PATH.exec(path);
      const onUpload = UPLOAD_FIELDS[path];
      if (onUpload !== undefined) upload[onUpload] = reason;
      else if (onMapping?.[1] !== undefined) mapping[onMapping[1]] = reason;
      else if (onRow?.[1] !== undefined && onRow[2] !== undefined)
        rows.push({ row: Number(onRow[1]), field: onRow[2], reason });
      else rest.push(reason);
    }
    const message =
      error.code === "import_has_errors"
        ? "Some rows changed since the check. Fix them in the file, or import the good rows only."
        : rest.length > 0
          ? rest.join(" ")
          : Object.keys(mapping).length > 0
            ? "Match the columns named below, then check again."
            : null;
    return { message, mapping, rows, finished: false, upload };
  }
  return { ...NO_FIELDS, message: toUserFacingError(error).title };
}
