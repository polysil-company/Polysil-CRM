import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";

import { RadioGroup, RadioGroupItem } from "./radio-group";

const meta = {
  title: "UI/RadioGroup",
  component: RadioGroup,
  args: { disabled: false, onValueChange: fn(), "aria-label": "Inquiry type" },
} satisfies Meta<typeof RadioGroup>;

export default meta;

type Story = StoryObj<typeof meta>;

const OPTIONS = [
  { value: "commercial", label: "Commercial" },
  { value: "subsidised", label: "Subsidised" },
  { value: "industrial", label: "Industrial" },
] as const;

export const Default: Story = {
  render: (args) => (
    <RadioGroup {...args} className="text-sm text-foreground">
      {OPTIONS.map((option) => (
        <label key={option.value} className="flex items-center gap-2.5">
          <RadioGroupItem value={option.value} />
          {option.label}
        </label>
      ))}
    </RadioGroup>
  ),
};

/** The chosen option uses the sun highlight, like a checked checkbox. */
export const Chosen: Story = {
  ...Default,
  args: { defaultValue: "subsidised" },
};

export const Disabled: Story = {
  ...Default,
  args: { defaultValue: "commercial", disabled: true },
};
