import { z } from "zod";

/**
 * ADMN-007 · Company settings (FS-036, `settings-amend-reopen-contract.md`): one row per
 * setting with its value and the rule for it. More keys arrive with other features, so the
 * screen renders each from its `kind`, never from a list of known keys.
 */

export const SETTING_KINDS = ["choice", "int", "roles", "bands", "slabs"] as const;

const settingWireSchema = z.object({
  key: z.string().min(1),
  /**
   * choice: one of `allowed`; int: a whole number in `min`..`max`; roles: role codes;
   * bands: four whole numbers, zero or more, strictly rising (FS-043); slabs: GST slabs as
   * strings such as "18", at least one, each a slab in force, none twice (FS-069).
   */
  kind: z.enum(SETTING_KINDS),
  value: z.union([z.string(), z.number(), z.array(z.string()), z.array(z.number())]),
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
    };

function toSetting(wire: z.output<typeof settingWireSchema>): Setting {
  const base = { key: wire.key, description: wire.description, updatedAt: wire.updated_at };
  const value = wire.value;
  switch (wire.kind) {
    case "choice":
      return {
        ...base,
        kind: "choice",
        value: typeof value === "string" ? value : String(value),
        allowed: wire.allowed ?? [],
      };
    case "int":
      return {
        ...base,
        kind: "int",
        value: typeof value === "number" ? value : Number(value),
        min: wire.min,
        max: wire.max,
      };
    case "roles":
      return {
        ...base,
        kind: "roles",
        value: Array.isArray(value) ? value.map(String) : [],
      };
    case "bands":
      return {
        ...base,
        kind: "bands",
        value: Array.isArray(value) ? value.map(Number) : [],
      };
    case "slabs":
      return {
        ...base,
        kind: "slabs",
        value: Array.isArray(value) ? value.map((slab) => String(Number(slab))) : [],
      };
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
