import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import type * as React from "react";

import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxStatus,
} from "./combobox";
import { Field, FieldDescription, FieldLabel } from "./field";

interface Place {
  id: string;
  name: string;
  level: string;
}

const PLACES: Place[] = [
  { id: "1", name: "Gondal", level: "Taluka in Rajkot" },
  { id: "2", name: "Jetpur", level: "Taluka in Rajkot" },
  { id: "3", name: "Keshod", level: "Taluka in Junagadh" },
  { id: "4", name: "Rajkot", level: "District" },
  { id: "5", name: "Virpur", level: "Village in Gondal" },
];

function PlaceCombobox({
  id,
  items = PLACES,
  defaultValue = null,
  disabled = false,
  showClear = false,
  status = null,
}: {
  id: string;
  items?: Place[];
  defaultValue?: Place | null;
  disabled?: boolean;
  showClear?: boolean;
  status?: string | null;
}): React.JSX.Element {
  return (
    <Field className="w-72">
      <FieldLabel htmlFor={id}>Territory</FieldLabel>
      <Combobox
        items={items}
        defaultValue={defaultValue}
        disabled={disabled}
        itemToStringLabel={(place: Place) => place.name}
        isItemEqualToValue={(item: Place, value: Place) => item.id === value.id}
      >
        <ComboboxInput id={id} placeholder="Search a place" showClear={showClear} />
        <ComboboxContent>
          <ComboboxStatus>{status}</ComboboxStatus>
          <ComboboxEmpty>No place matches.</ComboboxEmpty>
          <ComboboxList>
            {(place: Place) => (
              <ComboboxItem key={place.id} value={place}>
                <span className="flex flex-col">
                  <span>{place.name}</span>
                  <span className="text-xs text-muted-foreground">{place.level}</span>
                </span>
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
      <FieldDescription>Type to filter; arrow keys move, Enter chooses.</FieldDescription>
    </Field>
  );
}

const meta = {
  title: "UI/Combobox",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/** Filters the list as you type. For server-side search, pass `filter={null}` and the results. */
export const Default: Story = {
  render: () => <PlaceCombobox id="combobox-default" />,
};

/** A chosen value, with a button that clears it. */
export const WithValueAndClear: Story = {
  render: () => <PlaceCombobox id="combobox-value" defaultValue={PLACES[0] ?? null} showClear />,
};

/** The status line is announced to screen readers — use it for loading and hints. */
export const WithStatus: Story = {
  render: () => (
    <PlaceCombobox id="combobox-status" status="Districts — type to find a taluka or village." />
  ),
};

/** Nothing to choose from: the empty message shows in the list. */
export const Empty: Story = {
  render: () => <PlaceCombobox id="combobox-empty" items={[]} />,
};

export const Disabled: Story = {
  render: () => <PlaceCombobox id="combobox-disabled" defaultValue={PLACES[2] ?? null} disabled />,
};
