import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { AccessDenied } from "./access-denied";

const meta = {
  title: "Patterns/AccessDenied",
  component: AccessDenied,
} satisfies Meta<typeof AccessDenied>;

export default meta;

type Story = StoryObj<typeof meta>;

/** A page outside the user's permissions, opened by its address: the whole page, no reference. */
export const Default: Story = {};
