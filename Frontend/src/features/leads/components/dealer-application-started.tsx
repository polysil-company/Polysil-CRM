"use client";

import type * as React from "react";

import { Button } from "@/components/ui/button";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApplyLink } from "@/features/dealer-applications/components/apply-link";
import type { Lead } from "@/features/leads/api/leads.schemas";

export type DealerApplicationStart = NonNullable<Lead["dealerApplication"]>;

/** Why winning a dealership lead started no application, in words the officer can act on. */
export function notStartedReason(code: string): string {
  switch (code) {
    case "mobile_in_use":
      return "Their mobile number already belongs to a channel partner, so no application was started.";
    case "application_open":
      return "A dealer application is already open for their mobile number, so no new one was started.";
    case "mobile_invalid":
      return "Their mobile number isn't one an application can be sent to. Correct it on the lead, then start an application from Channel partners.";
    default:
      return "No dealer application was started.";
  }
}

/**
 * LEAD-015 · After a dealership lead is won (FS-053): the dealer application it started, with
 * the link to send the applicant. The link is shown only this once, so it can be copied or
 * sent on WhatsApp here. When none was started, says why.
 */
export function DealerApplicationStarted({
  lead,
  started,
}: {
  lead: Lead;
  started: DealerApplicationStart;
}): React.JSX.Element {
  const url = started.applyUrl;

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {url === null ? "Lead won, no application started" : "Dealer application started"}
        </DialogTitle>
        <DialogDescription>
          {url === null
            ? `${lead.customerName} is won.`
            : `${lead.customerName} is won. Send them this link to fill in their dealer application.`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        {url === null ? (
          <p className="text-sm text-foreground">{notStartedReason(started.notStarted ?? "")}</p>
        ) : (
          <ApplyLink url={url} name={lead.customerName} mobile={lead.phone} />
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" />}>Done</DialogClose>
      </DialogFooter>
    </>
  );
}
