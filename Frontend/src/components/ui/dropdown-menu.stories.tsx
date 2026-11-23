import {
  Call02Icon,
  Copy01Icon,
  Invoice03Icon,
  UserMultiple02Icon,
  WhatsappIcon,
} from "@hugeicons/core-free-icons";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import type * as React from "react";

import { Button } from "./button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "./dropdown-menu";
import { Icon } from "./icon";

function LeadActionsMenu(): React.JSX.Element {
  const [notifyOwner, setNotifyOwner] = useState(true);
  const [density, setDensity] = useState("comfortable");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="outline" />}>Lead actions</DropdownMenuTrigger>
      <DropdownMenuContent className="w-60">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Ramesh Patel</DropdownMenuLabel>
          <DropdownMenuItem>
            <Icon icon={Call02Icon} />
            Call
          </DropdownMenuItem>
          <DropdownMenuItem>
            <Icon icon={WhatsappIcon} />
            Message on WhatsApp
          </DropdownMenuItem>
          <DropdownMenuItem>
            <Icon icon={Invoice03Icon} />
            Create quotation
          </DropdownMenuItem>
          <DropdownMenuItem>
            <Icon icon={Copy01Icon} />
            Copy lead code
            <DropdownMenuShortcut>⌘C</DropdownMenuShortcut>
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            <Icon icon={UserMultiple02Icon} />
            Assign to
          </DropdownMenuSubTrigger>
          <DropdownMenuContent side="inline-end" sideOffset={-4} alignOffset={-4}>
            <DropdownMenuItem>Kiran Desai</DropdownMenuItem>
            <DropdownMenuItem>Meena Shah</DropdownMenuItem>
            <DropdownMenuItem disabled>Farhan Qureshi (on leave)</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenuSub>
        <DropdownMenuCheckboxItem
          checked={notifyOwner}
          onCheckedChange={(checked) => {
            setNotifyOwner(checked);
          }}
        >
          Notify the owner
        </DropdownMenuCheckboxItem>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuLabel>Row density</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={density}
            onValueChange={(value) => {
              if (typeof value === "string") {
                setDensity(value);
              }
            }}
          >
            <DropdownMenuRadioItem value="comfortable">Comfortable</DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="compact">Compact</DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive">Mark as lost</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const meta = {
  title: "UI/DropdownMenu",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/** Items, a submenu, a checkbox item, a radio group and a destructive action. */
export const LeadActions: Story = {
  render: () => <LeadActionsMenu />,
};
