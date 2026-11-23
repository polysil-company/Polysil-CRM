import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";

const meta = {
  title: "UI/Tabs",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/** Sections of one page. The indicator slides with CSS variables — no JavaScript animation. */
export const Underline: Story = {
  render: () => (
    <Tabs defaultValue="activity" className="w-96 max-w-full">
      <TabsList variant="underline" aria-label="Lead sections">
        <TabsTrigger variant="underline" value="activity">
          Activity
        </TabsTrigger>
        <TabsTrigger variant="underline" value="quotations">
          Quotations
        </TabsTrigger>
        <TabsTrigger variant="underline" value="documents" disabled>
          Documents
        </TabsTrigger>
      </TabsList>
      <TabsContent value="activity">
        <p className="text-sm text-muted-foreground">Twelve updates since the enquiry.</p>
      </TabsContent>
      <TabsContent value="quotations">
        <p className="text-sm text-muted-foreground">Two quotations, one awaiting approval.</p>
      </TabsContent>
      <TabsContent value="documents">
        <p className="text-sm text-muted-foreground">Subsidy documents arrive with SUBS-001.</p>
      </TabsContent>
    </Tabs>
  ),
};

/** Small switches inside a card or toolbar. */
export const Segmented: Story = {
  render: () => (
    <Tabs defaultValue="week">
      <TabsList variant="segmented" aria-label="Period">
        <TabsTrigger variant="segmented" value="today">
          Today
        </TabsTrigger>
        <TabsTrigger variant="segmented" value="week">
          This week
        </TabsTrigger>
        <TabsTrigger variant="segmented" value="month">
          This month
        </TabsTrigger>
      </TabsList>
      <TabsContent value="today">
        <p className="text-sm text-muted-foreground">6 follow-ups due today.</p>
      </TabsContent>
      <TabsContent value="week">
        <p className="text-sm text-muted-foreground">23 follow-ups due this week.</p>
      </TabsContent>
      <TabsContent value="month">
        <p className="text-sm text-muted-foreground">81 follow-ups due this month.</p>
      </TabsContent>
    </Tabs>
  ),
};
