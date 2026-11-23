import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import type * as React from "react";

import { Badge, type BadgeProps } from "./badge";

function BadgeVariants(props: BadgeProps): React.JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge {...props} variant="neutral">
        New
      </Badge>
      <Badge {...props} variant="primary">
        Contacted
      </Badge>
      <Badge {...props} variant="info">
        Quoted
      </Badge>
      <Badge {...props} variant="warning">
        Negotiation
      </Badge>
      <Badge {...props} variant="success">
        Won
      </Badge>
      <Badge {...props} variant="danger">
        Lost
      </Badge>
      <Badge {...props} variant="highlight">
        3 selected
      </Badge>
      <Badge {...props} variant="outline">
        Draft
      </Badge>
    </div>
  );
}

const meta = {
  title: "UI/Badge",
  component: Badge,
  args: { children: "Qualified", variant: "primary", size: "md", dot: false },
  argTypes: {
    variant: {
      control: "select",
      options: [
        "neutral",
        "primary",
        "success",
        "warning",
        "danger",
        "info",
        "highlight",
        "outline",
      ],
    },
    size: { control: "inline-radio", options: ["sm", "md"] },
    render: { control: false },
  },
} satisfies Meta<typeof Badge>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Playground: Story = {};

/** Lead statuses use these. Status colour is never the only signal — the text says it too. */
export const Variants: Story = {
  render: (args) => <BadgeVariants {...args} />,
};

export const WithDot: Story = {
  args: { dot: true },
  render: (args) => <BadgeVariants {...args} />,
};

export const Small: Story = {
  args: { size: "sm" },
  render: (args) => <BadgeVariants {...args} />,
};
