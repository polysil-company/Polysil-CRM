import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Badge } from "./badge";
import { Button } from "./button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "./card";

const FOLLOW_UPS = [
  { name: "Ramesh Patel", note: "Confirm site visit", overdue: true },
  { name: "Meena Shah", note: "Send revised quotation", overdue: true },
  { name: "Farhan Qureshi", note: "Collect subsidy documents", overdue: false },
];

const meta = {
  title: "UI/Card",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Card className="w-80 max-w-full">
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>Follow-ups due today</CardTitle>
          <CardDescription>3 customers expect a call.</CardDescription>
        </div>
        <Badge variant="warning" size="sm">
          2 overdue
        </Badge>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col divide-y divide-border">
          {FOLLOW_UPS.map((item) => (
            <li key={item.name} className="flex items-center justify-between gap-3 py-2.5">
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-sm font-medium text-foreground">{item.name}</span>
                <span className="truncate text-xs text-muted-foreground">{item.note}</span>
              </span>
              {item.overdue ? (
                <Badge variant="danger" size="sm">
                  Overdue
                </Badge>
              ) : null}
            </li>
          ))}
        </ul>
      </CardContent>
      <CardFooter>
        <Button variant="ghost" size="sm">
          View all follow-ups
        </Button>
      </CardFooter>
    </Card>
  ),
};

export const Simple: Story = {
  render: () => (
    <Card className="w-80 max-w-full">
      <CardHeader>
        <CardTitle>Schemes</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Monsoon offer: 5% off drip laterals for orders placed before 30 September.
        </p>
      </CardContent>
    </Card>
  ),
};
