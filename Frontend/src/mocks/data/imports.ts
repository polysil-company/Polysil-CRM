import type {
  ImportBatchWire,
  ImportCheckWire,
  ImportKind,
} from "@/features/imports/api/imports.schemas";

/**
 * MSTR-007 · The mock's side of the Excel import (backend `api/domain/imports/fields.py`). The
 * fields, labels and help lines are the backend's. The mock reads a `.csv` itself; it has no
 * Excel reader, so any `.xlsx` gets the sample workbook for its kind below. The backend reads
 * both.
 */

export interface MockImportField {
  readonly key: string;
  readonly label: string;
  readonly required: boolean;
  readonly help: string;
  /** Header names that suggest the field, compared without spaces, case or punctuation. */
  readonly aliases: readonly string[];
}

const PRODUCT_FIELDS: readonly MockImportField[] = [
  {
    key: "item_code",
    label: "Item code",
    required: false,
    help: "The product's item code. Give this or the description.",
    aliases: ["itemcode", "code", "sku", "productcode", "partno", "itemno"],
  },
  {
    key: "description",
    label: "Description",
    required: false,
    help: "The product's description, exactly as in the catalogue. Give this or the item code.",
    aliases: ["description", "product", "productname", "item", "itemname", "particulars"],
  },
];

export const MOCK_IMPORT_FIELDS: Readonly<Record<ImportKind, readonly MockImportField[]>> = {
  partners: [
    {
      key: "partner_type",
      label: "Type",
      required: true,
      help: "Distributor, dealer or sub-dealer.",
      aliases: ["type", "partnertype", "category", "dealertype", "level"],
    },
    {
      key: "code",
      label: "Code",
      required: true,
      help: "Unique across all partners.",
      aliases: ["code", "partnercode", "dealercode", "distributorcode", "id"],
    },
    {
      key: "name",
      label: "Name",
      required: true,
      help: "The partner's business name.",
      aliases: [
        "name",
        "partnername",
        "dealername",
        "firmname",
        "businessname",
        "distributorname",
        "firm",
        "shopname",
      ],
    },
    {
      key: "state",
      label: "State",
      required: true,
      help: "A state's name or its two-letter code.",
      aliases: ["state", "statename", "statecode"],
    },
    {
      key: "district",
      label: "District",
      required: false,
      help: "A district in that state. Without one, the partner sits at the state.",
      aliases: ["district", "dist", "districtname", "city"],
    },
    {
      key: "parent_code",
      label: "Parent code",
      required: false,
      help: "The code of the partner one type up: a dealer's distributor, a sub-dealer's dealer. It may be a row in this file.",
      aliases: [
        "parentcode",
        "parent",
        "distributor",
        "distributorcode",
        "underdealer",
        "dealer",
        "under",
      ],
    },
    {
      key: "contact_name",
      label: "Contact name",
      required: false,
      help: "The person to speak to.",
      aliases: [
        "contactname",
        "contact",
        "contactperson",
        "owner",
        "ownername",
        "proprietor",
        "person",
      ],
    },
    {
      key: "mobile",
      label: "Mobile",
      required: false,
      help: "An Indian mobile, in any common form.",
      aliases: [
        "mobile",
        "mob",
        "mobileno",
        "mobilenumber",
        "phone",
        "phoneno",
        "contactno",
        "contactnumber",
        "whatsapp",
        "cell",
      ],
    },
    {
      key: "email",
      label: "Email",
      required: false,
      help: "",
      aliases: ["email", "emailid", "mail", "emailaddress"],
    },
    {
      key: "address",
      label: "Address",
      required: false,
      help: "",
      aliases: ["address", "fulladdress", "addr"],
    },
    {
      key: "gstin",
      label: "GSTIN",
      required: false,
      help: "15 characters.",
      aliases: ["gstin", "gst", "gstno", "gstnumber", "gstinno"],
    },
    {
      key: "pan",
      label: "PAN",
      required: false,
      help: "10 characters.",
      aliases: ["pan", "panno", "pannumber"],
    },
    {
      key: "is_gst_registered",
      label: "GST registered",
      required: false,
      help: "Yes or no. Without the column, yes when a GSTIN is given.",
      aliases: ["gstregistered", "registered", "isgstregistered"],
    },
    {
      key: "credit_limit",
      label: "Credit limit",
      required: false,
      help: "Rupees, at most two decimals.",
      aliases: ["creditlimit", "credit", "limit"],
    },
    {
      key: "payment_terms_days",
      label: "Payment terms (days)",
      required: false,
      help: "0 to 365.",
      aliases: ["paymentterms", "paymenttermsdays", "creditdays", "terms", "days"],
    },
  ],
  price_list_items: [
    ...PRODUCT_FIELDS,
    {
      key: "rate",
      label: "Rate",
      required: true,
      help: "Rupees per unit, more than 0, at most two decimals. More is refused, not rounded.",
      aliases: ["rate", "price", "unitprice", "amount", "listprice", "netrate"],
    },
  ],
  lines: [
    ...PRODUCT_FIELDS,
    {
      key: "qty",
      label: "Quantity",
      required: true,
      help: "More than 0, in the product's unit.",
      aliases: ["qty", "quantity", "nos", "units"],
    },
    {
      key: "discount_pct",
      label: "Discount %",
      required: false,
      help: "0 to 100.",
      aliases: ["discount", "discountpct", "disc", "discount1"],
    },
    {
      key: "discount2_pct",
      label: "Discount 2 %",
      required: false,
      help: "0 to 100.",
      aliases: ["discount2", "disc2"],
    },
    {
      key: "discount3_pct",
      label: "Discount 3 %",
      required: false,
      help: "0 to 100.",
      aliases: ["discount3", "disc3"],
    },
  ],
};

/** At least one of each group must be matched. */
export const MOCK_IMPORT_ONE_OF: Readonly<Record<ImportKind, readonly (readonly string[])[]>> = {
  partners: [],
  price_list_items: [["item_code", "description"]],
  lines: [["item_code", "description"]],
};

export interface MockSheet {
  readonly name: string;
  /** Every row including the header row(s), cell by cell. */
  readonly rows: readonly (readonly string[])[];
}

/**
 * The sample workbook the mock answers for any `.xlsx`: a client's sheet as it might arrive,
 * with a second sheet so the sheet picker shows, and a mistake or two for the review step.
 */
export const MOCK_SAMPLE_WORKBOOKS: Readonly<Record<ImportKind, readonly MockSheet[]>> = {
  price_list_items: [
    {
      name: "Rates",
      rows: [
        ["Item Code", "Product", "Unit", "Net Rate"],
        ["PL-1001", "", "MTR", "15.20"],
        ["PL-1002", "", "NOS", "3.95"],
        ["", "SCREEN FILTER 2 INCH 20 M3/HR", "NOS", "4999"],
        ["PL-1004", "", "NOS", "abc"],
        ["PL-9999", "", "NOS", "120"],
      ],
    },
    { name: "Notes", rows: [["Note"], ["Rates from the October circular."]] },
  ],
  lines: [
    {
      name: "Order",
      rows: [
        ["Sr", "Particulars", "Qty", "Disc %"],
        ["1", "HDPE LATERAL 16 MM 2.5 KG/CM2", "500", "5"],
        ["2", "INLINE DRIPPER 4 LPH", "120", ""],
        ["3", "SCREEN FILTER 2 INCH 20 M3/HR", "2", "0"],
        ["4", "A PRODUCT WE DON'T SELL", "10", ""],
      ],
    },
  ],
  partners: [
    {
      name: "Dealers",
      rows: [
        ["Type", "Dealer Code", "Firm Name", "State", "District", "Under", "Owner", "Mobile"],
        [
          "Distributor",
          "D-NEW-01",
          "Saurashtra Agro Distributors",
          "Gujarat",
          "Rajkot",
          "",
          "Mahesh Patel",
          "98250 11223",
        ],
        [
          "Dealer",
          "DL-NEW-01",
          "Gondal Krishi Seva",
          "GJ",
          "Rajkot",
          "D-NEW-01",
          "Ketan Shah",
          "+91 98765 01234",
        ],
        [
          "Dealer",
          "DL-NEW-02",
          "Bhavnagar Irrigation Point",
          "Gujarat",
          "Bhavnagar",
          "D-NEW-01",
          "",
          "9898",
        ],
        ["Sub-dealer", "", "Village Agro", "Gujarat", "", "DL-NEW-01", "", ""],
      ],
    },
  ],
};

/** "Net Rate" → "netrate": how a header is compared with a field's names. */
export function headerKey(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/**
 * A CSV as rows of cells: commas, double quotes around cells that hold commas, quotes or line
 * breaks, and "" for a quote inside one. Enough for what a spreadsheet saves.
 */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  const source = text.replace(/^﻿/, "");
  for (let index = 0; index < source.length; index += 1) {
    const char = source.charAt(index);
    if (quoted) {
      if (char === '"' && source.charAt(index + 1) === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        cell += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(cell.trim());
      cell = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && source.charAt(index + 1) === "\n") index += 1;
      row.push(cell.trim());
      rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }
  if (cell !== "" || row.length > 0) {
    row.push(cell.trim());
    rows.push(row);
  }
  return rows.filter((cells) => cells.some((value) => value !== ""));
}

/** A blank header reads "Column C"; a repeated one gets " (2)", as the backend names them. */
export function nameHeaders(raw: readonly string[]): string[] {
  const seen = new Map<string, number>();
  return raw.map((header, index) => {
    const name =
      header.trim() === "" ? `Column ${String.fromCharCode(65 + (index % 26))}` : header.trim();
    const count = (seen.get(name) ?? 0) + 1;
    seen.set(name, count);
    return count === 1 ? name : `${name} (${String(count)})`;
  });
}

/** Field to column from the headers' names; a column once, a field once. */
export function suggestMapping(
  kind: ImportKind,
  headers: readonly string[],
): Record<string, number> {
  const out: Record<string, number> = {};
  const taken = new Set<number>();
  for (const field of MOCK_IMPORT_FIELDS[kind]) {
    for (const alias of [headerKey(field.key), headerKey(field.label), ...field.aliases]) {
      const column = headers.findIndex(
        (header, index) => !taken.has(index) && headerKey(header) === alias,
      );
      if (column >= 0) {
        out[field.key] = column;
        taken.add(column);
        break;
      }
    }
  }
  return out;
}

/** `mapping.<key>` to reason, as the backend refuses a mapping it cannot check. */
export function mappingProblems(
  kind: ImportKind,
  mapping: Readonly<Record<string, number>>,
  width: number,
): Record<string, string> {
  const fields = new Map(MOCK_IMPORT_FIELDS[kind].map((field) => [field.key, field]));
  const problems: Record<string, string> = {};
  const seen = new Map<number, string>();
  for (const [key, column] of Object.entries(mapping)) {
    const field = fields.get(key);
    if (field === undefined) {
      problems[`mapping.${key}`] = "not a field of this import";
    } else if (column < 0 || column >= width) {
      problems[`mapping.${key}`] = `no column ${String(column)}`;
    } else if (seen.has(column)) {
      problems[`mapping.${key}`] = `that column is already ${seen.get(column) ?? ""}`;
    } else {
      seen.set(column, field.label);
    }
  }
  for (const field of fields.values()) {
    if (field.required && !(field.key in mapping)) {
      problems[`mapping.${field.key}`] ??= "required";
    }
  }
  for (const group of MOCK_IMPORT_ONE_OF[kind]) {
    const [first] = group;
    if (first !== undefined && !group.some((key) => key in mapping)) {
      problems[`mapping.${first}`] ??= `match ${group.join(" or ")}`;
    }
  }
  return problems;
}

/** One upload, as the mock keeps it. */
export interface MockImportBatch {
  readonly wire: ImportBatchWire;
  /** The data rows under the header row, each with its row number in the person's sheet. */
  readonly rows: readonly { readonly row: number; readonly cells: readonly string[] }[];
  /** The whole file, to read another sheet or header row from. */
  readonly sheets: readonly MockSheet[];
  readonly owner: string;
  status: "uploaded" | "checked" | "committed" | "discarded";
  mapping: Record<string, number> | null;
  options: { mode: "replace" | "merge" };
  check: ImportCheckWire | null;
}
