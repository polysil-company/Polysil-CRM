"use client";

import { Copy01Icon, Tick02Icon, WhatsappIcon } from "@hugeicons/core-free-icons";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Icon } from "@/components/ui/icon";
import { useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";

/** The message that goes with the link on WhatsApp. */
function whatsappText(name: string, url: string): string {
  return `Hello ${name}, thank you for your interest in becoming a Polysil dealer. Please fill in your dealer application here: ${url}`;
}

/**
 * LEAD-015, CHNL-007 · A dealer application's link (FS-053), with Copy and Share on WhatsApp.
 * The backend keeps only the token's hash, so the link is shown once: after starting the
 * application, or after a new link.
 */
export function ApplyLink({
  url,
  name,
  mobile,
}: {
  url: string;
  /** Whom the WhatsApp message greets. */
  name: string;
  /** Any Indian form; only its digits are used. */
  mobile: string;
}): React.JSX.Element {
  const { copied, copy } = useCopyToClipboard();
  const whatsappNumber = mobile.replace(/\D/g, "");

  return (
    <div className="flex flex-col gap-3">
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
          href={`https://wa.me/${whatsappNumber}?text=${encodeURIComponent(whatsappText(name, url))}`}
          target="_blank"
          rel="noreferrer"
          className={buttonVariants({ variant: "outline" })}
        >
          <Icon icon={WhatsappIcon} />
          Share on WhatsApp
        </a>
      </div>
    </div>
  );
}
