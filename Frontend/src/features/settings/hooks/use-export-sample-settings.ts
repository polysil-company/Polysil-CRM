"use client";

import { useQuery } from "@tanstack/react-query";

import type { SamplePricing } from "@/features/orders/api/orders.schemas";
import type { TaxTreatment } from "@/features/quotations/api/quotations.schemas";
import { settingsQueryOptions } from "@/features/settings/api/settings.queries";
import type { Setting } from "@/features/settings/api/settings.schemas";

/** What a new export or sample takes from the company settings (FS-042). */
export interface ExportSampleSettings {
  /** A new export's treatment: `export_tax_treatment` lut → export_lut, igst → export_igst. */
  readonly exportTreatment: TaxTreatment;
  readonly samplePricing: SamplePricing;
  /** The largest sample, in rupees of list value; null until the settings are read. */
  readonly sampleMaxValue: number | null;
  /** True once the settings were read; until then the defaults stand. */
  readonly known: boolean;
}

function choiceOf(settings: readonly Setting[], key: string): string | null {
  const setting = settings.find((item) => item.key === key);
  return setting?.kind === "choice" ? setting.value : null;
}

/**
 * The export and sample settings from `GET /settings`, with the backend's own defaults (lut,
 * free) when they can't be read: the settings are staff only.
 */
export function exportSampleSettingsFrom(
  settings: readonly Setting[] | undefined,
): ExportSampleSettings {
  if (settings === undefined) {
    return {
      exportTreatment: "export_lut",
      samplePricing: "free",
      sampleMaxValue: null,
      known: false,
    };
  }
  const max = settings.find((item) => item.key === "sample_max_value");
  return {
    exportTreatment:
      choiceOf(settings, "export_tax_treatment") === "igst" ? "export_igst" : "export_lut",
    samplePricing: choiceOf(settings, "sample_pricing") === "charged" ? "charged" : "free",
    sampleMaxValue: max?.kind === "int" ? max.value : null,
    known: true,
  };
}

/** SO-010 · Reads the settings only while an export or a sample is being made. */
export function useExportSampleSettings(enabled: boolean): ExportSampleSettings {
  const query = useQuery({ ...settingsQueryOptions(), enabled, retry: false });
  return exportSampleSettingsFrom(query.data);
}
