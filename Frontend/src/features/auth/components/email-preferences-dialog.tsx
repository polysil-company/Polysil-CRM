"use client";

import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useEmailPreferences } from "@/features/auth/api/auth.mutations";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/auth/components/email-preferences-dialog.tsx",
  dataId: "AUTH-008",
});

/**
 * AUTH-008 · Your two email switches (FS-078): updates you haven't seen, and a morning summary
 * of the day's tasks. Render it inside a `Dialog`; the menu owns the open state and shows the
 * item only while the backend can send email to you.
 */
export function EmailPreferencesDialogContent({
  notices,
  morningSummary,
  onDone,
}: {
  notices: boolean;
  morningSummary: boolean;
  onDone: () => void;
}): React.JSX.Element {
  const save = useEmailPreferences();
  const idempotency = useIdempotencyKey();
  const [draftNotices, setDraftNotices] = useState(notices);
  const [draftMorning, setDraftMorning] = useState(morningSummary);
  const unchanged = draftNotices === notices && draftMorning === morningSummary;

  const run = useAsyncAction({
    action: () => {
      const body = { notices: draftNotices, morning_summary: draftMorning };
      return save.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleSaveEmailPreferences",
    dataId: "AUTH-008",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Email preferences saved");
      onDone();
    },
    onError: (error) => {
      toast.error("Not saved", { description: toUserFacingError(error).description });
    },
  });

  return (
    <DialogContent size="sm">
      <form
        noValidate
        aria-label="Email preferences"
        className="flex min-h-0 flex-1 flex-col"
        onSubmit={(event) => {
          event.preventDefault();
          if (unchanged) return;
          void run.run();
        }}
      >
        <DialogHeader>
          <DialogTitle>Email</DialogTitle>
          <DialogDescription>What the CRM sends to your email address.</DialogDescription>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-4">
          <Switch
            label="Updates I haven't seen"
            hint="A notification still unread 10 minutes after it came is emailed; several go in one email."
            checked={draftNotices}
            onChange={setDraftNotices}
          />
          <Switch
            label="Morning summary"
            hint="At 8 am, Monday to Saturday, when you have tasks due that day or overdue."
            checked={draftMorning}
            onChange={setDraftMorning}
          />
        </DialogBody>
        <DialogFooter>
          <DialogClose render={<Button type="button" variant="outline" disabled={run.isBusy} />}>
            Cancel
          </DialogClose>
          <Button
            type="submit"
            disabled={unchanged ? run.state === "idle" : null}
            state={run.state}
            loadingLabel="Saving…"
            successLabel="Saved"
            errorLabel="Not saved"
          >
            Save
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

function Switch({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}): React.JSX.Element {
  return (
    <label className="flex items-start gap-3 text-sm text-foreground">
      <Checkbox className="mt-0.5" checked={checked} onCheckedChange={onChange} />
      <span className="flex flex-col gap-0.5">
        <span className="font-medium">{label}</span>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </span>
    </label>
  );
}
