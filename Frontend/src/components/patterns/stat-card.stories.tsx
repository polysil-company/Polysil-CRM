import {
  Clock01Icon,
  IndianRupeeIcon,
  Target02Icon,
  UserAdd01Icon,
} from "@hugeicons/core-free-icons";
import type { Decorator, Meta, StoryObj } from "@storybook/nextjs-vite";

import { describeTrend } from "./sparkline";
import { StatCard, StatCardSkeleton } from "./stat-card";

const PIPELINE = [3.1, 3.4, 3.2, 3.8, 4.1, 4.5];
const NEW_LEADS = [96, 104, 99, 112, 120, 128];
const CONVERSION = [21.4, 20.8, 19.9, 19.1, 18.7, 18.2];
const OVERDUE = [22, 21, 19, 18, 16, 14];

const fixedWidth: Decorator = (Story) => (
  <div className="w-72 max-w-full">
    <Story />
  </div>
);

const meta = {
  title: "Patterns/StatCard",
  component: StatCard,
  args: {
    label: "Pipeline value",
    value: "₹4.5 Cr",
    icon: IndianRupeeIcon,
    delta: 12.4,
    increaseIsGood: true,
    trend: PIPELINE,
    trendLabel: describeTrend(PIPELINE, "Pipeline value, last 6 weeks"),
    footnote: "Open leads this quarter",
  },
  argTypes: { icon: { control: false } },
} satisfies Meta<typeof StatCard>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Improving: Story = {
  decorators: [fixedWidth],
};

/** For overdue work a decrease is good news, so the badge is green. */
export const DecreaseIsGood: Story = {
  decorators: [fixedWidth],
  args: {
    label: "Overdue follow-ups",
    value: "14",
    icon: Clock01Icon,
    delta: -22.2,
    increaseIsGood: false,
    trend: OVERDUE,
    trendLabel: describeTrend(OVERDUE, "Overdue follow-ups, last 6 weeks"),
    footnote: "Down from 18 last week",
  },
};

export const Worsening: Story = {
  decorators: [fixedWidth],
  args: {
    label: "Conversion rate",
    value: "18.2%",
    icon: Target02Icon,
    delta: -3.1,
    trend: CONVERSION,
    trendLabel: describeTrend(CONVERSION, "Conversion rate, last 6 weeks"),
    footnote: "Won out of closed, this quarter",
  },
};

export const WithoutTrend: Story = {
  decorators: [fixedWidth],
  render: () => (
    <StatCard label="New leads" value="128" icon={UserAdd01Icon} footnote="This week" />
  ),
};

/** The dashboard row: four cards, two columns on tablets, one on phones. */
export const DashboardRow: Story = {
  parameters: { layout: "padded" },
  render: () => (
    <div className="grid w-full max-w-6xl gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        label="Pipeline value"
        value="₹4.5 Cr"
        icon={IndianRupeeIcon}
        delta={12.4}
        trend={PIPELINE}
        trendLabel={describeTrend(PIPELINE, "Pipeline value, last 6 weeks")}
        footnote="Open leads this quarter"
      />
      <StatCard
        label="New leads"
        value="128"
        icon={UserAdd01Icon}
        delta={6.7}
        trend={NEW_LEADS}
        trendLabel={describeTrend(NEW_LEADS, "New leads, last 6 weeks")}
        footnote="This week"
      />
      <StatCard
        label="Conversion rate"
        value="18.2%"
        icon={Target02Icon}
        delta={-3.1}
        trend={CONVERSION}
        trendLabel={describeTrend(CONVERSION, "Conversion rate, last 6 weeks")}
        footnote="Won out of closed"
      />
      <StatCard
        label="Overdue follow-ups"
        value="14"
        icon={Clock01Icon}
        delta={-22.2}
        increaseIsGood={false}
        trend={OVERDUE}
        trendLabel={describeTrend(OVERDUE, "Overdue follow-ups, last 6 weeks")}
        footnote="Down from 18 last week"
      />
    </div>
  ),
};

/** Mirrors the loaded row line for line, so nothing shifts when data arrives. */
export const Loading: Story = {
  parameters: { layout: "padded" },
  render: () => (
    <div
      role="status"
      aria-label="Loading dashboard"
      className="grid w-full max-w-6xl gap-3 sm:grid-cols-2 xl:grid-cols-4"
    >
      <StatCardSkeleton />
      <StatCardSkeleton />
      <StatCardSkeleton />
      <StatCardSkeleton />
    </div>
  ),
};
