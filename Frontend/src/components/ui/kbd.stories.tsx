import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Kbd, KbdGroup } from "./kbd";

const meta = {
  title: "UI/Kbd",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/** The shortcuts the app shell supports today. On Windows the command key shows as Ctrl. */
export const Shortcuts: Story = {
  render: () => (
    <ul className="flex w-72 flex-col gap-3 text-sm text-foreground">
      <li className="flex items-center justify-between gap-6">
        <span>Open the command menu</span>
        <KbdGroup>
          <Kbd>⌘</Kbd>
          <Kbd>K</Kbd>
        </KbdGroup>
      </li>
      <li className="flex items-center justify-between gap-6">
        <span>Search</span>
        <Kbd>/</Kbd>
      </li>
      <li className="flex items-center justify-between gap-6">
        <span>Close a dialog or menu</span>
        <Kbd>Esc</Kbd>
      </li>
    </ul>
  ),
};
