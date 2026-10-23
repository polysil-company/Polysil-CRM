import {
  Add01Icon,
  FilterRemoveIcon,
  Invoice03Icon,
  UserAdd01Icon,
} from "@hugeicons/core-free-icons";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";

import { EmptyState } from "./empty-state";

const meta = {
  title: "Patterns/EmptyState",
  component: EmptyState,
  args: {
    icon: UserAdd01Icon,
    title: "No leads yet",
    description:
      "Leads from WhatsApp, the website and QR codes appear here. You can also add one yourself.",
  },
  argTypes: { icon: { control: false }, action: { control: false } },
} satisfies Meta<typeof EmptyState>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Nothing exists yet: explain where data will come from and offer the first step. */
export const FirstRun: Story = {
  args: {
    action: (
      <Button>
        <Icon icon={Add01Icon} />
        New lead
      </Button>
    ),
  },
};

/** Data exists but the filters hide it: say so, and offer the way out. */
export const NoMatches: Story = {
  args: {
    icon: FilterRemoveIcon,
    title: "No leads match these filters",
    description: "Try removing a filter, or search by phone number instead.",
    action: <Button variant="outline">Clear filters</Button>,
  },
};

/** A module that is planned but not built: honest, with its Data ID. */
export const PlannedModule: Story = {
  args: {
    icon: Invoice03Icon,
    title: "Quotations are on the way",
    description: "This module is planned as QUOT-001.",
  },
};
