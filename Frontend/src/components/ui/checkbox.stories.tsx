import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";

import { Checkbox } from "./checkbox";

const meta = {
  title: "UI/Checkbox",
  component: Checkbox,
  args: { disabled: false, onCheckedChange: fn() },
} satisfies Meta<typeof Checkbox>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (args) => (
    <label className="flex items-center gap-2.5 text-sm text-foreground">
      <Checkbox {...args} />
      Send WhatsApp updates to the customer
    </label>
  ),
};

/** Checked and indeterminate use the sun highlight — the same colour as a selected table row. */
export const States: Story = {
  render: (args) => (
    <div className="flex flex-col gap-3 text-sm text-foreground">
      <label className="flex items-center gap-2.5">
        <Checkbox {...args} />
        Unchecked
      </label>
      <label className="flex items-center gap-2.5">
        <Checkbox {...args} defaultChecked />
        Checked
      </label>
      <label className="flex items-center gap-2.5">
        <Checkbox {...args} indeterminate />
        Some rows on this page selected
      </label>
      <label className="flex items-center gap-2.5">
        <Checkbox {...args} disabled />
        Disabled
      </label>
      <label className="flex items-center gap-2.5">
        <Checkbox {...args} defaultChecked disabled />
        Checked and disabled
      </label>
      <label className="flex items-center gap-2.5">
        <Checkbox {...args} aria-invalid />
        Accept the subsidy terms (required)
      </label>
    </div>
  ),
};
