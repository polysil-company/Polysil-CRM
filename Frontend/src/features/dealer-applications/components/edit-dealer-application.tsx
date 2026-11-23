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
import { Field, FieldLabel } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  PARTNER_TYPES,
  type PartnerType,
} from "@/features/dealer-applications/api/data-sheet.schemas";
import { usePatchDealerApplication } from "@/features/dealer-applications/api/dealer-applications.mutations";
import type {
  DealerApplication,
  StaffApplicationFieldsRequest,
} from "@/features/dealer-applications/api/dealer-applications.schemas";
import { PARTNER_TYPE_LABELS } from "@/features/dealer-applications/lib/dealer-application-labels";
import { GstinDetails } from "@/features/partners/components/gstin-details";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

import {
  changedFields,
  DealerFieldsEditor,
  draftOf,
  fieldProblems,
  isMaskedAccount,
  problemsFromServer,
  type DealerFieldProblems,
  type DealerFieldsDraft,
} from "./dealer-application-fields";
import { refusalOf, RefusalNote, type Refusal } from "./dealer-application-refusals";

const log = createLogger({
  file: "features/dealer-applications/components/edit-dealer-application.tsx",
  dataId: "CHNL-007",
});

/**
 * CHNL-007 · Staff fill or correct the applicant's fields (while draft, returned or submitted).
 * Only what changed is sent; under a GSTIN, the GST record offers its names. While draft or
 * returned, staff may also change the type (FS-071); the backend refuses it once a deposit is
 * recorded, and says so.
 */
export function EditDealerApplication({
  application,
  onClose,
}: {
  application: DealerApplication;
  onClose: () => void;
}): React.JSX.Element {
  const patch = usePatchDealerApplication();
  const idempotency = useIdempotencyKey();
  const [initial] = useState<DealerFieldsDraft>(() => draftOf(application));
  const [draft, setDraft] = useState<DealerFieldsDraft>(initial);
  const [shown, setShown] = useState(false);
  const [server, setServer] = useState<DealerFieldProblems>({});
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [partnerType, setPartnerType] = useState<PartnerType>(application.partnerType);
  const typeOpen = application.status === "draft" || application.status === "returned";
  const local = fieldProblems(draft);
  const problems: DealerFieldProblems = { ...(shown ? local : {}), ...server };
  const body: StaffApplicationFieldsRequest = {
    ...changedFields(draft, initial),
    ...(partnerType === application.partnerType ? {} : { partner_type: partnerType }),
  };
  const unchanged = Object.keys(body).length === 0;

  const save = useAsyncAction({
    action: () =>
      patch.mutateAsync({
        applicationId: application.id,
        body,
        idempotencyKey: idempotency.keyFor(body),
      }),
    logger: log,
    fn: "handleEditDealerApplication",
    dataId: "CHNL-007",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Application updated");
      onClose();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null) {
        setServer(problemsFromServer(fields));
        return;
      }
      const { refusal: next, stale } = refusalOf(error);
      if (stale) {
        toast.error(next.title, { description: next.message });
        onClose();
        return;
      }
      setRefusal(next);
    },
  });

  return (
    <form
      noValidate
      aria-label="Edit the application"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServer({});
        setRefusal(null);
        if (Object.keys(local).length > 0 || unchanged) return;
        void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Edit {application.firmName}&apos;s details</DialogTitle>
        <DialogDescription>
          Fill in or correct what the applicant gave. Only what you change is saved.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        {typeOpen ? (
          <Field>
            <FieldLabel id="edit-dealer-app-type-label">The application makes a</FieldLabel>
            <RadioGroup<PartnerType>
              aria-labelledby="edit-dealer-app-type-label"
              value={partnerType}
              onValueChange={setPartnerType}
              className="flex-row flex-wrap gap-5"
            >
              {PARTNER_TYPES.map((type) => (
                <label key={type} className="flex items-center gap-2 text-sm text-foreground">
                  <RadioGroupItem value={type} />
                  {PARTNER_TYPE_LABELS[type]}
                </label>
              ))}
            </RadioGroup>
          </Field>
        ) : null}
        <DealerFieldsEditor
          idPrefix="edit-dealer-app"
          draft={draft}
          onDraftChange={(next) => {
            setDraft(next);
            setServer({});
          }}
          problems={problems}
          maskedAccount={
            isMaskedAccount(application.bankAccountNo) ? application.bankAccountNo : null
          }
          workingCapitalTotal={application.dataSheet.workingCapitalTotalLakhs}
          gstinCheck={(gstin) => (
            <GstinDetails
              gstin={gstin}
              onUse={(fill) => {
                setDraft((current) => ({
                  ...current,
                  firmName: fill.name,
                  pan: fill.pan ?? current.pan,
                  address: fill.address ?? current.address,
                }));
              }}
            />
          )}
        />
        <RefusalNote refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          disabled={unchanged ? save.state === "idle" : false}
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Save changes
        </Button>
      </DialogFooter>
    </form>
  );
}
