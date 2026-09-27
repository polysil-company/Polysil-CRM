import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import type * as React from "react";
import { fn } from "storybook/test";

import {
  FilterPill,
  SingleFilterPill,
  type FilterOption,
  type FilterPillProps,
} from "./filter-pill";

const STAGE_OPTIONS: readonly FilterOption<string>[] = [
  { value: "new", label: "New", count: 42 },
  { value: "contacted", label: "Contacted", count: 31 },
  { value: "qualified", label: "Qualified", count: 18 },
  { value: "won", label: "Won", count: 12 },
  { value: "lost", label: "Lost", count: 9 },
];

const SOURCE_OPTIONS: readonly FilterOption<string>[] = [
  { value: "whatsapp", label: "WhatsApp" },
  { value: "website", label: "Website" },
  { value: "qr_code", label: "QR Code" },
  { value: "employee", label: "Employee" },
];

/** Keeps the selection in local state so the story is interactive; the app keeps it in the URL. */
function FilterPillDemo(props: FilterPillProps<string>): React.JSX.Element {
  const [selected, setSelected] = useState<readonly string[]>(props.selected);

  return (
    <FilterPill
      {...props}
      selected={selected}
      onChange={(next) => {
        setSelected(next);
        props.onChange(next);
      }}
    />
  );
}

function SingleFilterPillDemo({
  initial,
  options,
}: {
  initial: string | null;
  options: readonly FilterOption<string>[];
}): React.JSX.Element {
  const [selected, setSelected] = useState<string | null>(initial);

  return (
    <SingleFilterPill
      label="Source"
      options={options}
      selected={selected}
      onChange={setSelected}
      emptyMessage="Loading sources…"
    />
  );
}

const meta = {
  title: "Patterns/FilterPill",
  component: FilterPill,
  args: { label: "Stage", options: STAGE_OPTIONS, selected: [], onChange: fn() },
  argTypes: { icon: { control: false } },
  render: (args) => <FilterPillDemo {...args} />,
} satisfies Meta<typeof FilterPill>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Dashed while nothing is selected. */
export const Unset: Story = {};

/** One value: the pill names it. */
export const OneSelected: Story = {
  args: { selected: ["qualified"] },
};

/** Several values: the pill counts them. */
export const SeveralSelected: Story = {
  args: { selected: ["new", "contacted", "qualified"] },
};

export const WithoutCounts: Story = {
  args: { label: "Source", options: SOURCE_OPTIONS },
};

/** For filters the API takes one value of: radios, so choosing one replaces the last. */
export const SingleChoice: Story = {
  render: () => <SingleFilterPillDemo initial="website" options={SOURCE_OPTIONS} />,
};

/** Options that come from the API show a message until they arrive. */
export const SingleChoiceLoading: Story = {
  render: () => <SingleFilterPillDemo initial={null} options={[]} />,
};
