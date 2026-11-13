import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { describeTrend, Sparkline } from "./sparkline";

const RISING = [3, 4, 3, 5, 7, 6, 9];
const FALLING = [18, 17, 15, 16, 12, 11, 9];
const FLAT = [6, 6, 6, 6, 6];

const meta = {
  title: "Patterns/Sparkline",
  component: Sparkline,
  args: {
    values: RISING,
    label: describeTrend(RISING, "Leads per week"),
    tone: "primary",
    area: true,
  },
  argTypes: {
    tone: { control: "select", options: ["primary", "success", "danger", "muted"] },
  },
} satisfies Meta<typeof Sparkline>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Screen readers hear the summary: "Leads per week: rising, from 3 to 9". */
export const Rising: Story = {};

export const Falling: Story = {
  args: {
    values: FALLING,
    label: describeTrend(FALLING, "Overdue follow-ups per week"),
    tone: "danger",
  },
};

export const Flat: Story = {
  args: { values: FLAT, label: describeTrend(FLAT, "Dispatches per day"), tone: "muted" },
};

export const LineOnly: Story = {
  args: { area: false },
};

/** Fewer than two points: a dash instead of a misleading line. */
export const NotEnoughData: Story = {
  args: { values: [4], label: describeTrend([4], "Leads per week") },
};
