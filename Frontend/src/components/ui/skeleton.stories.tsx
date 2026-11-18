import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Card } from "./card";
import { Skeleton } from "./skeleton";

const ROWS = [0, 1, 2, 3];

const meta = {
  title: "UI/Skeleton",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/**
 * A skeleton mirrors the layout it stands in for — same heights and gaps — so
 * nothing moves when data arrives. The container is the status; blocks stay hidden.
 */
export const ListRows: Story = {
  render: () => (
    <Card role="status" aria-label="Loading follow-ups" className="w-80 max-w-full gap-3 p-4">
      {ROWS.map((row) => (
        <div key={row} className="flex items-center gap-3">
          <Skeleton className="size-8 shrink-0 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3.5 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </Card>
  ),
};
