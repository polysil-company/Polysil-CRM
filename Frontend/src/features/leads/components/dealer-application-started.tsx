"use client";

import { Copy01Icon, Tick02Icon, WhatsappIcon } from "@hugeicons/core-free-icons";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import type { Lead } from "@/features/leads/api/leads.schemas";
import { useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";

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

/** The message that goes with the link on WhatsApp. */
function whatsappText(name: string, url: string): string {
  return `Hello ${name}, thank you for your interest in becoming a Polysil dealer. Please fill in your dealer application here: ${url}`;
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
  const { copied, copy } = useCopyToClipboard();
  const url = started.applyUrl;
  const whatsappNumber = lead.phone.replace(/\D/g, "");

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
          <>
            <div className="flex flex-col gap-1.5 rounded-lg border border-border p-3">
              <span className="text-xs text-muted-foreground">Application link</span>
              <span className="font-mono text-xs break-all text-foreground">{url}</span>
            </div>
            <p className="text-xs text-muted-foreground">
              The link is shown only now. Copy it or send it before you close this.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                aria-label={copied ? "Link copied" : "Copy the application link"}
                onClick={() => {
                  void copy(url).then((done) => {
                    if (!done) toast.error("Couldn't copy: select the link and copy it yourself.");
                  });
                }}
              >
                <Icon icon={copied ? Tick02Icon : Copy01Icon} />
                {copied ? "Copied" : "Copy link"}
              </Button>
              <a
                href={`https://wa.me/${whatsappNumber}?text=${encodeURIComponent(whatsappText(lead.customerName, url))}`}
                target="_blank"
                rel="noreferrer"
                className={buttonVariants({ variant: "outline" })}
              >
                <Icon icon={WhatsappIcon} />
                Share on WhatsApp
              </a>
            </div>
          </>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" />}>Done</DialogClose>
      </DialogFooter>
    </>
  );
}
