import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import type * as React from "react";
import { fn } from "storybook/test";

import { FilterPill, type FilterOption, type FilterPillProps } from "./filter-pill";

const STATUS_OPTIONS: readonly FilterOption<string>[] = [
  { value: "new", label: "New", count: 42 },
  { value: "contacted", label: "Contacted", count: 31 },
  { value: "qualified", label: "Qualified", count: 18 },
  { value: "won", label: "Won", count: 12 },
  { value: "lost", label: "Lost", count: 9 },
];

const SOURCE_OPTIONS: readonly FilterOption<string>[] = [
  { value: "whatsapp", label: "WhatsApp" },
  { value: "website", label: "Website" },
  { value: "qr_code", label: "QR code" },
  { value: "employee", label: "Field staff" },
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

const meta = {
  title: "Patterns/FilterPill",
  component: FilterPill,
  args: { label: "Status", options: STATUS_OPTIONS, selected: [], onChange: fn() },
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
