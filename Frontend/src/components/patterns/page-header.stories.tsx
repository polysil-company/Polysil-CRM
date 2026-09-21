import { Add01Icon } from "@hugeicons/core-free-icons";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { PageHeader } from "./page-header";

const meta = {
  title: "Patterns/PageHeader",
  component: PageHeader,
  parameters: { layout: "padded" },
  args: {
    title: "Leads",
    description: "Every enquiry from WhatsApp, the website, QR codes and field staff.",
  },
  argTypes: { meta: { control: false }, actions: { control: false }, children: { control: false } },
} satisfies Meta<typeof PageHeader>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** Actions sit on the right on desktop and wrap below the title on phones. */
export const WithActions: Story = {
  args: {
    meta: <Badge>137</Badge>,
    actions: (
      <>
        <Button variant="outline">Export</Button>
        <Button>
          <Icon icon={Add01Icon} />
          New lead
        </Button>
      </>
    ),
  },
};

export const WithTabs: Story = {
  args: {
    title: "Sales",
    description: "Leads, quotations and sales orders.",
    children: (
      <Tabs defaultValue="leads">
        <TabsList variant="underline" aria-label="Sales sections">
          <TabsTrigger variant="underline" value="leads">
            Leads
          </TabsTrigger>
          <TabsTrigger variant="underline" value="quotations">
            Quotations
          </TabsTrigger>
          <TabsTrigger variant="underline" value="sales-orders">
            Sales orders
          </TabsTrigger>
        </TabsList>
      </Tabs>
    ),
  },
};
