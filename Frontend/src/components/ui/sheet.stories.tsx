import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import type * as React from "react";

import { Button } from "./button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "./sheet";

const FOLLOW_UPS = [
  { time: "10:30", name: "Ramesh Patel", note: "Confirm site visit" },
  { time: "12:00", name: "Meena Shah", note: "Send revised quotation" },
  { time: "15:15", name: "Farhan Qureshi", note: "Collect subsidy documents" },
  { time: "17:45", name: "Kiran Desai", note: "Payment reminder" },
];

function FollowUpsSheet({ side }: { side: "left" | "right" | "bottom" }): React.JSX.Element {
  return (
    <Sheet>
      <SheetTrigger render={<Button variant="outline" />}>Open from the {side}</SheetTrigger>
      <SheetContent side={side}>
        <SheetHeader>
          <SheetTitle>Today&apos;s follow-ups</SheetTitle>
          <SheetDescription>Four customers expect to hear from you.</SheetDescription>
        </SheetHeader>
        <ul className="flex flex-1 scrollbar-thin flex-col divide-y divide-border overflow-y-auto px-4 pb-4">
          {FOLLOW_UPS.map((item) => (
            <li key={item.name} className="flex items-baseline gap-3 py-3">
              <span className="w-12 shrink-0 text-xs text-muted-foreground tabular-nums">
                {item.time}
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-sm font-medium text-foreground">{item.name}</span>
                <span className="truncate text-xs text-muted-foreground">{item.note}</span>
              </span>
            </li>
          ))}
        </ul>
      </SheetContent>
    </Sheet>
  );
}

const meta = {
  title: "UI/Sheet",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/** Details and secondary work, sliding in with the drawer curve. */
export const Right: Story = { render: () => <FollowUpsSheet side="right" /> };

/** The mobile navigation uses this side. */
export const Left: Story = { render: () => <FollowUpsSheet side="left" /> };

export const Bottom: Story = { render: () => <FollowUpsSheet side="bottom" /> };
