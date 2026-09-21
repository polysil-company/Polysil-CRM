import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import type * as React from "react";

import { Button } from "./button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./dialog";

const ACTIVITY = [
  "Enquiry received on WhatsApp",
  "Called — interested in drip for 4.5 acres of cotton",
  "Site visit booked for Thursday",
  "Soil report shared by the customer",
  "Subsidy documents requested",
  "Quotation Q-2041 drafted",
  "Discount approval requested from the State Manager",
  "Approval granted",
  "Quotation sent on WhatsApp",
  "Customer asked for a second option with sprinklers",
  "Revised quotation sent",
  "Advance payment promised by Monday",
];

function AssignLeadDialog({
  size = "md",
  motion = "default",
}: {
  size?: "sm" | "md" | "lg";
  motion?: "default" | "none";
}): React.JSX.Element {
  return (
    <Dialog>
      <DialogTrigger render={<Button variant="outline" />}>Assign lead</DialogTrigger>
      <DialogContent size={size} motion={motion}>
        <DialogHeader>
          <DialogTitle>Assign lead</DialogTitle>
          <DialogDescription>
            Ramesh Patel · Vadodara. The new owner gets a WhatsApp message with the details.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <p className="text-sm text-muted-foreground">
            Kiran Desai covers Vadodara and has 12 open leads. Assigning moves every follow-up with
            the lead.
          </p>
        </DialogBody>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
          <DialogClose render={<Button />}>Assign to Kiran</DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const meta = {
  title: "UI/Dialog",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/** Centred and scaling in on tablets and up. Switch the viewport to a phone to see the bottom sheet. */
export const Default: Story = {
  render: () => <AssignLeadDialog />,
};

export const Confirm: Story = {
  render: () => (
    <Dialog>
      <DialogTrigger render={<Button variant="destructive" />}>Mark as lost</DialogTrigger>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Mark this lead as lost?</DialogTitle>
          <DialogDescription>
            Follow-ups are cancelled. You can reopen the lead later from its history.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>Keep open</DialogClose>
          <DialogClose render={<Button variant="destructive" />}>Mark as lost</DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  ),
};

/** Long content scrolls inside the body; the header and footer stay put. */
export const LongContent: Story = {
  render: () => (
    <Dialog>
      <DialogTrigger render={<Button variant="outline" />}>View activity</DialogTrigger>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Activity</DialogTitle>
          <DialogDescription>Ramesh Patel, newest last.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <ol className="flex flex-col divide-y divide-border">
            {[...ACTIVITY, ...ACTIVITY].map((item, index) => (
              <li key={`${item}-${index}`} className="py-3 text-sm text-foreground">
                {item}
              </li>
            ))}
          </ol>
        </DialogBody>
        <DialogFooter>
          <DialogClose render={<Button />}>Done</DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  ),
};

/** For dialogs opened many times a day, such as the command menu: no animation at all. */
export const WithoutMotion: Story = {
  render: () => <AssignLeadDialog motion="none" />,
};
