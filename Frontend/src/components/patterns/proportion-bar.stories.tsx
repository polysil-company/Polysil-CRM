import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { ProportionBar } from "./proportion-bar";

const meta = {
  title: "Patterns/ProportionBar",
  component: ProportionBar,
  args: { value: 62, max: 100, tone: "primary" },
  argTypes: {
    value: { control: { type: "range", min: 0, max: 100, step: 1 } },
    marker: { control: { type: "range", min: 0, max: 100, step: 1 } },
    tone: { control: "select", options: ["primary", "success", "warning", "danger"] },
  },
  decorators: [
    (Story) => (
      <div className="w-72">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof ProportionBar>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Playground: Story = {};

/** A target line on the same scale: short of it, and past it. */
export const WithMarker: Story = {
  render: (args) => (
    <ul className="flex flex-col gap-3">
      <li>
        <ProportionBar {...args} value={55} marker={80} />
      </li>
      <li>
        <ProportionBar {...args} value={100} marker={70} />
      </li>
      <li>
        <ProportionBar {...args} value={0} marker={100} />
      </li>
    </ul>
  ),
};

export const Empty: Story = {
  args: { value: 0 },
};
