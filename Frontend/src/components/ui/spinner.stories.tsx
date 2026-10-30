import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { ProgressRing, Spinner } from "./spinner";

const PROGRESS_STEPS = [0, 25, 60, 100];

const meta = {
  title: "UI/Spinner",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/** One circular loader for the whole app. It spins fast on purpose — slow spinners feel slow. */
export const Spinners: Story = {
  render: () => (
    <div className="flex flex-col items-start gap-4">
      <div className="flex items-center gap-6 text-primary">
        <Spinner label="Loading leads" />
        <Spinner label="Loading dashboard" className="size-5" />
        <Spinner label="Loading reports" className="size-6 text-muted-foreground" />
      </div>
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner />
        Refreshing leads…
      </p>
    </div>
  ),
};

/** Determinate progress, as used inside an uploading Button. Always paired with text. */
export const Progress: Story = {
  render: () => (
    <ul className="flex flex-col gap-3">
      {PROGRESS_STEPS.map((value) => (
        <li key={value} className="flex items-center gap-3 text-sm text-foreground">
          <ProgressRing value={value} className="size-5 text-primary" />
          <span className="tabular-nums">{value}% uploaded</span>
        </li>
      ))}
    </ul>
  ),
};
