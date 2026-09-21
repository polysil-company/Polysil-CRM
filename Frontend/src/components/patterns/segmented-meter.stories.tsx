import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { SegmentedMeter } from "./segmented-meter";

const THRESHOLD_VALUES = [15, 50, 85];

const meta = {
  title: "Patterns/SegmentedMeter",
  component: SegmentedMeter,
  args: { value: 72, max: 100, segments: 5, label: "Win probability", showValue: true },
  argTypes: {
    value: { control: { type: "range", min: 0, max: 100, step: 1 } },
    segments: { control: { type: "range", min: 3, max: 10, step: 1 } },
    tone: { control: "select", options: ["primary", "success", "warning", "danger"] },
  },
} satisfies Meta<typeof SegmentedMeter>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Playground: Story = {};

/** Without a fixed tone: low reads as danger, middle as warning, high as success. */
export const Thresholds: Story = {
  render: (args) => (
    <ul className="flex flex-col gap-3">
      {THRESHOLD_VALUES.map((value) => (
        <li key={value}>
          <SegmentedMeter {...args} value={value} label={`Win probability, lead ${value}`} />
        </li>
      ))}
    </ul>
  ),
};

export const FixedTone: Story = {
  args: { value: 40, tone: "primary", label: "Profile completeness" },
};

export const WithoutValue: Story = {
  args: { showValue: false },
};
