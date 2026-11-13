import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { SarthiChariot, SarthiVision } from "./sarthi-vision";

const meta = {
  title: "Patterns/SarthiVision",
  component: SarthiVision,
} satisfies Meta<typeof SarthiVision>;

export default meta;

type Story = StoryObj<typeof meta>;

/** APP-013 · The phone's card under the sign-in form. */
export const Card: Story = {
  render: (args) => (
    <section
      aria-label="Our vision"
      className="flex max-w-sm items-center gap-3 rounded-xl border border-border bg-card p-3"
    >
      <SarthiChariot className="size-14" />
      <SarthiVision {...args} />
    </section>
  ),
};

/** APP-013 · On the brand panel beside sign-in, on a wide screen. */
export const OnPrimary: Story = {
  args: { tone: "primary" },
  render: (args) => (
    <div className="flex max-w-lg flex-col gap-6 rounded-2xl bg-primary p-8 text-primary-foreground">
      <SarthiChariot className="size-32 ring-4 ring-primary-foreground/30" />
      <SarthiVision {...args} className="border-l-4 border-primary-foreground/40 pl-4" />
    </div>
  ),
};
