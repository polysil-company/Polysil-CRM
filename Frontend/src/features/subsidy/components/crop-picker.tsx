"use client";

import type * as React from "react";

import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox";
import type { SubsidyCrop } from "@/features/subsidy/api/subsidy.schemas";

export interface CropPickerProps {
  id: string;
  crops: readonly SubsidyCrop[];
  /** The crop's name exactly as `GET /subsidy/crops` returned it; null for none. */
  value: string | null;
  onValueChange: (crop: string | null) => void;
  placeholder: string;
  "aria-invalid"?: true | undefined;
  "aria-describedby"?: string | undefined;
}

/**
 * SUBS-003 · Pick a crop from the scheme's table, typing to narrow it. Each option shows its
 * standard lateral spacing, because the subsidy runs at the larger of that and the designer's.
 */
export function CropPicker({
  id,
  crops,
  value,
  onValueChange,
  placeholder,
  ...aria
}: CropPickerProps): React.JSX.Element {
  const selected = crops.find((row) => row.crop === value) ?? null;
  return (
    <Combobox
      items={crops}
      value={selected}
      onValueChange={(next: SubsidyCrop | null) => {
        onValueChange(next?.crop ?? null);
      }}
      itemToStringLabel={(row: SubsidyCrop) => row.crop}
      isItemEqualToValue={(item: SubsidyCrop, current: SubsidyCrop) => item.crop === current.crop}
    >
      <ComboboxInput id={id} placeholder={placeholder} autoComplete="off" showClear {...aria} />
      <ComboboxContent>
        <ComboboxEmpty>No crop matches. The scheme tabulates only these.</ComboboxEmpty>
        <ComboboxList>
          {(row: SubsidyCrop) => (
            <ComboboxItem key={row.crop} value={row}>
              <span className="flex min-w-0 flex-1 items-baseline justify-between gap-3">
                <span className="truncate">{row.crop}</span>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  {row.standardSpacing} m
                </span>
              </span>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
