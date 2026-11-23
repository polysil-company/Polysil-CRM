"use client";

import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { usePatchCustomer } from "@/features/customers/api/customers.mutations";
import {
  CONSENT_CHANNELS,
  type ConsentChannel,
  type CustomerDetail,
} from "@/features/customers/api/customers.schemas";
import { CONSENT_CHANNEL_LABELS } from "@/features/customers/lib/customer-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatFullDate } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/customers/components/consent-dialog.tsx",
  dataId: "LEAD-018",
});

/**
 * LEAD-018 · Record the customer's consent now, saying how it was given, or withdraw it.
 * Recording it again the same way keeps the first date.
 */
export function ConsentForm({
  customer,
  onDone,
}: {
  customer: CustomerDetail;
  onDone: () => void;
}): React.JSX.Element {
  const given = customer.consentGivenAt !== null;
  const [channel, setChannel] = useState<ConsentChannel>(customer.consentChannel ?? "whatsapp");
  const mutation = usePatchCustomer();
  const idempotency = useIdempotencyKey();

  const save = useAsyncAction({
    action: () => {
      const body = given
        ? { consent_given: false }
        : { consent_given: true, consent_channel: channel };
      return mutation.mutateAsync({
        customerId: customer.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: customer.id, ...body }),
      });
    },
    logger: log,
    fn: given ? "handleWithdrawConsent" : "handleRecordConsent",
    dataId: "LEAD-018",
    onSuccess: () => {
      idempotency.reset();
      toast.success(given ? "Consent withdrawn" : "Consent recorded", {
        description: customer.name,
      });
      onDone();
    },
    onError: (error) => {
      toast.error(given ? "Consent not withdrawn" : "Consent not recorded", {
        description: toUserFacingError(error).description,
      });
    },
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>{given ? "Withdraw consent?" : "Record consent"}</DialogTitle>
        <DialogDescription>
          {given && customer.consentGivenAt !== null
            ? `Given ${formatFullDate(customer.consentGivenAt)}${customer.consentChannel === null ? "" : `, ${CONSENT_CHANNEL_LABELS[customer.consentChannel].toLowerCase()}`}. Withdrawing it is recorded on the timeline.`
            : `That ${customer.name} agreed to be contacted, from today.`}
        </DialogDescription>
      </DialogHeader>
      {given ? (
        <DialogBody />
      ) : (
        <DialogBody>
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium text-foreground">How it was given</legend>
            <RadioGroup<ConsentChannel>
              aria-label="How it was given"
              value={channel}
              onValueChange={setChannel}
              className="flex flex-col gap-2"
            >
              {CONSENT_CHANNELS.map((item) => (
                <label key={item} className="flex items-center gap-2 text-sm text-foreground">
                  <RadioGroupItem value={item} />
                  {CONSENT_CHANNEL_LABELS[item]}
                </label>
              ))}
            </RadioGroup>
          </fieldset>
        </DialogBody>
      )}
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          variant={given ? "destructive" : "primary"}
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
          onClick={() => {
            void save.run();
          }}
        >
          {given ? "Withdraw" : "Record consent"}
        </Button>
      </DialogFooter>
    </div>
  );
}
