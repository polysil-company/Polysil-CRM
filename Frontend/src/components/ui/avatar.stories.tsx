import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Avatar, AvatarFallback, getInitials } from "./avatar";

const PEOPLE = ["Ramesh Patel", "Meena Shah", "Kiran", "Farhan Qureshi"];
const SIZES = ["xs", "sm", "md", "lg"] as const;

const meta = {
  title: "UI/Avatar",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/** Initials are the fallback until a photo loads — and the default, since most users have none. */
export const Sizes: Story = {
  render: () => (
    <ul className="flex items-end gap-4">
      {SIZES.map((size) => (
        <li key={size} className="flex flex-col items-center gap-2">
          <Avatar size={size}>
            <AvatarFallback>{getInitials("Ramesh Patel")}</AvatarFallback>
          </Avatar>
          <code className="font-mono text-xs text-muted-foreground">{size}</code>
        </li>
      ))}
    </ul>
  ),
};

/** Always next to the person's name — the initials alone are not an accessible label. */
export const WithNames: Story = {
  render: () => (
    <ul className="flex flex-col gap-3">
      {PEOPLE.map((name) => (
        <li key={name} className="flex items-center gap-2.5">
          <Avatar size="sm">
            <AvatarFallback>{getInitials(name)}</AvatarFallback>
          </Avatar>
          <span className="text-sm text-foreground">{name}</span>
        </li>
      ))}
    </ul>
  ),
};
