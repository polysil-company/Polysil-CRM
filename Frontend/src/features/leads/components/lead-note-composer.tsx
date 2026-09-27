"use client";

import { useId, useRef, useState } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Kbd, KbdGroup } from "@/components/ui/kbd";
import { Textarea } from "@/components/ui/textarea";
import { useAddLeadNote } from "@/features/leads/api/leads.mutations";
import { LEAD_NOTE_MAX_LENGTH } from "@/features/leads/api/leads.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { useModifierKeyLabel } from "@/hooks/use-modifier-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { readFieldErrors } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/leads/components/lead-note-composer.tsx",
  dataId: "LEAD-006",
});

/** Show the remaining characters once a note gets this close to the limit. */
const COUNTER_THRESHOLD = 200;

/** "1 character", "1,200 characters" */
function characters(count: number): string {
  return `${formatNumber(count)} ${count === 1 ? "character" : "characters"}`;
}

export interface LeadNoteComposerProps {
  leadId: string;
}

/**
 * LEAD-006 · Write a note on the lead. Notes run to several lines, so Enter adds a line and
 * Ctrl/⌘ + Enter saves. A retry of the same text reuses its Idempotency-Key, so a save whose
 * reply was lost is replayed by the backend rather than added twice. A failed save keeps
 * the text in the box.
 */
export function LeadNoteComposer({ leadId }: LeadNoteComposerProps): React.JSX.Element {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const addNote = useAddLeadNote();
  const idempotency = useIdempotencyKey();
  const modifier = useModifierKeyLabel();
  const fieldId = useId();
  const hintId = `${fieldId}-hint`;
  const errorId = `${fieldId}-error`;

  const note = draft.trim();
  const remaining = LEAD_NOTE_MAX_LENGTH - draft.length;
  const tooLong = remaining < 0;

  const save = useAsyncAction({
    action: (text: string) =>
      addNote.mutateAsync({
        leadId,
        body: { note: text },
        idempotencyKey: idempotency.keyFor({ leadId, note: text }),
      }),
    logger: log,
    fn: "handleAddNote",
    dataId: "LEAD-006",
    onSuccess: () => {
      idempotency.reset();
      setDraft("");
      setError(null);
    },
    onError: (saveError) => {
      setError(readFieldErrors(saveError)?.note ?? toUserFacingError(saveError).title);
      textareaRef.current?.focus();
    },
  });

  const canSave = note !== "" && !tooLong && !save.isBusy;

  const handleSave = (): void => {
    if (!canSave) {
      return;
    }
    setError(null);
    void save.run(note);
  };

  const describedBy = [hintId, error === null ? null : errorId].filter(Boolean).join(" ");

  return (
    <form
      noValidate
      aria-label="Add a note"
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        handleSave();
      }}
    >
      <label htmlFor={fieldId} className="sr-only">
        Note
      </label>
      <Textarea
        id={fieldId}
        ref={textareaRef}
        value={draft}
        rows={2}
        placeholder="Add a note — a call, a visit, what the farmer asked for…"
        aria-invalid={tooLong || error !== null ? true : undefined}
        aria-describedby={describedBy}
        className="max-h-60 min-h-16 resize-none"
        onChange={(event) => {
          setDraft(event.target.value);
          if (error !== null) {
            setError(null);
          }
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
            event.preventDefault();
            handleSave();
          }
        }}
      />
      {error === null ? null : (
        <p id={errorId} role="alert" className="text-xs text-danger">
          {error} Your note is still here — try again.
        </p>
      )}
      <div className="flex items-center justify-between gap-3">
        <p id={hintId} className="text-2xs text-subtle-foreground" aria-live="polite">
          {remaining <= COUNTER_THRESHOLD ? (
            <span className={tooLong ? "text-danger" : undefined}>
              {tooLong
                ? `${characters(-remaining)} over the ${formatNumber(LEAD_NOTE_MAX_LENGTH)} limit`
                : `${characters(remaining)} left`}
            </span>
          ) : (
            <span className="pointer-coarse:hidden">
              <KbdGroup>
                <Kbd>{modifier}</Kbd>
                <Kbd>Enter</Kbd>
              </KbdGroup>{" "}
              to save
            </span>
          )}
        </p>
        <Button
          type="submit"
          size="sm"
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          disabled={!canSave && save.state === "idle"}
        >
          Add note
        </Button>
      </div>
    </form>
  );
}
