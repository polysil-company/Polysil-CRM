import { Call02Icon, Copy01Icon, Invoice03Icon, WhatsappIcon } from "@hugeicons/core-free-icons";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Button } from "./button";
import { Icon, type IconGlyph } from "./icon";
import { Kbd } from "./kbd";
import { Tooltip, TooltipContent, TooltipTrigger } from "./tooltip";

interface ToolbarAction {
  readonly label: string;
  readonly icon: IconGlyph;
  readonly shortcut: string;
}

const ACTIONS: readonly ToolbarAction[] = [
  { label: "Call customer", icon: Call02Icon, shortcut: "C" },
  { label: "Message on WhatsApp", icon: WhatsappIcon, shortcut: "W" },
  { label: "Create quotation", icon: Invoice03Icon, shortcut: "Q" },
  { label: "Copy lead code", icon: Copy01Icon, shortcut: "Y" },
];

const meta = {
  title: "UI/Tooltip",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Tooltip>
      <TooltipTrigger
        render={<Button variant="outline" size="icon-md" aria-label="Call customer" />}
      >
        <Icon icon={Call02Icon} />
      </TooltipTrigger>
      <TooltipContent>Call customer</TooltipContent>
    </Tooltip>
  ),
};

/**
 * The first tooltip waits 400ms. Slide to a neighbour and it opens instantly,
 * with no animation — the toolbar feels fast without tooltips firing by accident.
 */
export const Toolbar: Story = {
  render: () => (
    <div
      role="group"
      aria-label="Lead actions"
      className="flex items-center gap-1 rounded-lg border border-border bg-card p-1 shadow-xs"
    >
      {ACTIONS.map((action) => (
        <Tooltip key={action.label}>
          <TooltipTrigger
            render={<Button variant="ghost" size="icon-sm" aria-label={action.label} />}
          >
            <Icon icon={action.icon} />
          </TooltipTrigger>
          <TooltipContent>
            {action.label}
            <Kbd>{action.shortcut}</Kbd>
          </TooltipContent>
        </Tooltip>
      ))}
    </div>
  ),
};
