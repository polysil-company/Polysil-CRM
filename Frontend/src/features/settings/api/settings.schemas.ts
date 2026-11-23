import { z } from "zod";

/**
 * ADMN-007 · Company settings (FS-036, `settings-amend-reopen-contract.md`): one row per
 * setting with its value and the rule for it. More keys arrive with other features, so the
 * screen renders each from its `kind`, never from a list of known keys.
 */

export const SETTING_KINDS = [
  "choice",
  "int",
  "roles",
  "bands",
  "slabs",
  "set",
  "staff_roles",
] as const;

type KnownKind = (typeof SETTING_KINDS)[number];

const settingWireSchema = z.object({
  key: z.string().min(1),
  /**
   * choice: one of `allowed`; int: a whole number in `min`..`max`; roles: role codes;
   * bands: four whole numbers, zero or more, strictly rising (FS-043); slabs: GST slabs as
   * strings such as "18", at least one, each a slab in force, none twice (FS-069); set: some of
   * `allowed`, none twice; staff_roles: at least one staff role code (FS-071). Any other kind is
   * read, and shown read-only, so a kind added later can't take the whole page down.
   */
  kind: z.string().min(1),
  value: z.unknown(),
  allowed: z.array(z.string()).nullable(),
  min: z.number().int().nullable(),
  max: z.number().int().nullable(),
  description: z.string(),
  updated_at: z.string().min(1),
});

export type SettingWire = z.input<typeof settingWireSchema>;

/** A setting as screens read it: its value normalised for its kind. */
export type Setting =
  | {
      readonly key: string;
      readonly kind: "choice";
      readonly value: string;
      readonly allowed: readonly string[];
      readonly description: string;
      readonly updatedAt: string;
    }
  | {
      readonly key: string;
      readonly kind: "int";
      readonly value: number;
      readonly min: number | null;
      readonly max: number | null;
      readonly description: string;
      readonly updatedAt: string;
    }
  | {
      readonly key: string;
      readonly kind: "roles";
      readonly value: readonly string[];
      readonly description: string;
      readonly updatedAt: string;
    }
  | {
      readonly key: string;
      readonly kind: "bands";
      readonly value: readonly number[];
      readonly description: string;
      readonly updatedAt: string;
    }
  | {
      readonly key: string;
      readonly kind: "slabs";
      readonly value: readonly string[];
      readonly description: string;
      readonly updatedAt: string;
    }
  | {
      readonly key: string;
      readonly kind: "set";
      readonly value: readonly string[];
      readonly allowed: readonly string[];
      readonly description: string;
      readonly updatedAt: string;
    }
  | {
      readonly key: string;
      readonly kind: "staff_roles";
      readonly value: readonly string[];
      readonly description: string;
      readonly updatedAt: string;
    }
  | {
      readonly key: string;
      /** A kind this screen doesn't know yet: shown as text, never edited. */
      readonly kind: "unknown";
      readonly wireKind: string;
      readonly value: string;
      readonly description: string;
      readonly updatedAt: string;
    };

function isKnownKind(kind: string): kind is KnownKind {
  return SETTING_KINDS.some((known) => known === kind);
}

function listOf(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

/** A value of a kind the screen doesn't know, as plain text. */
function textOf(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(textOf).join(", ");
  return JSON.stringify(value);
}

function toSetting(wire: z.output<typeof settingWireSchema>): Setting {
  const base = { key: wire.key, description: wire.description, updatedAt: wire.updated_at };
  const value = wire.value;
  const kind = wire.kind;
  if (!isKnownKind(kind)) {
    return { ...base, kind: "unknown", wireKind: kind, value: textOf(value) };
  }
  switch (kind) {
    case "choice":
      return { ...base, kind: "choice", value: textOf(value), allowed: wire.allowed ?? [] };
    case "int":
      return {
        ...base,
        kind: "int",
        value: typeof value === "number" ? value : Number(textOf(value)),
        min: wire.min,
        max: wire.max,
      };
    case "roles":
      return { ...base, kind: "roles", value: listOf(value).map(textOf) };
    case "bands":
      return { ...base, kind: "bands", value: listOf(value).map((band) => Number(textOf(band))) };
    case "slabs":
      return {
        ...base,
        kind: "slabs",
        value: listOf(value).map((slab) => String(Number(textOf(slab)))),
      };
    case "set":
      return {
        ...base,
        kind: "set",
        value: listOf(value).map(textOf),
        allowed: wire.allowed ?? [],
      };
    case "staff_roles":
      return { ...base, kind: "staff_roles", value: listOf(value).map(textOf) };
  }
}

/** GET and PATCH /settings both answer the full list. */
export const settingsSchema = z
  .object({ data: z.array(settingWireSchema) })
  .transform(({ data }) => data.map(toSetting));

/** PATCH /settings: only the settings that change, by key. */
export interface SettingsPatchRequest {
  readonly values: Readonly<
    Record<string, string | number | readonly string[] | readonly number[]>
  >;
}
