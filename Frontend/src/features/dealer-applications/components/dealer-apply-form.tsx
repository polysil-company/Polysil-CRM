"use client";

import { Delete02Icon, File01Icon, SentIcon, Upload04Icon } from "@hugeicons/core-free-icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Notice } from "@/components/patterns/notice";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  applicantGstinQueryOptions,
  dealerApplicationKeys,
} from "@/features/dealer-applications/api/dealer-applications.queries";
import {
  patchApplicantFields,
  removeApplicantDocument,
  submitApplicantApplication,
  uploadApplicantDocument,
} from "@/features/dealer-applications/api/dealer-apply.api";
import {
  APPLICANT_DOCUMENT_TYPES,
  type ApplicantDocument,
  type ApplicantDocumentType,
  type ApplicantView,
} from "@/features/dealer-applications/api/dealer-apply.schemas";
import {
  APPLICANT_DOCUMENT_LABELS,
  missingLabel,
} from "@/features/dealer-applications/lib/dealer-application-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

import {
  changedFields,
  DealerFieldsEditor,
  draftOf,
  fieldProblems,
  type DealerFieldProblems,
  type DealerFieldsDraft,
} from "./dealer-application-fields";
import { refusalOf } from "./dealer-application-refusals";

const log = createLogger({
  file: "features/dealer-applications/components/dealer-apply-form.tsx",
  dataId: "CHNL-008",
});

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf,.heic,.heif";

function isNoSession(error: unknown): boolean {
  return isApiError(error) && error.status === 403;
}

/**
 * CHNL-008 · The applicant's form once verified: the firm's details (saved as they go), the
 * documents, and Submit once nothing is missing. A returned application shows what to fix.
 */
export function DealerApplyForm({
  token,
  session,
  view,
  onSessionLost,
}: {
  token: string;
  session: string;
  view: ApplicantView;
  onSessionLost: () => void;
}): React.JSX.Element {
  const queryClient = useQueryClient();
  const applicant = { token, session };
  const fields = view.fields;
  const [initial, setInitial] = useState<DealerFieldsDraft | null>(() =>
    fields === null ? null : draftOf(fields),
  );
  const [draft, setDraft] = useState<DealerFieldsDraft | null>(initial);
  const [shown, setShown] = useState(false);
  const [server, setServer] = useState<DealerFieldProblems>({});

  const refresh = (): void => {
    void queryClient.invalidateQueries({
      queryKey: [...dealerApplicationKeys.all, "applicant", token],
    });
  };
  const sessionLost = (): void => {
    toast.error("Verify your mobile again", { description: "Your session ended." });
    onSessionLost();
  };

  const local = draft === null ? {} : fieldProblems(draft);
  const problems: DealerFieldProblems = { ...(shown ? local : {}), ...server };
  const body = draft === null || initial === null ? {} : changedFields(draft, initial);
  const unsaved = Object.keys(body).length > 0;

  const save = useAsyncAction({
    action: () => patchApplicantFields(applicant, body),
    logger: log,
    fn: "handleSaveApplicantFields",
    dataId: "CHNL-008",
    onSuccess: (next) => {
      queryClient.setQueryData([...dealerApplicationKeys.all, "applicant", token, session], next);
      if (next.fields !== null) {
        const saved = draftOf(next.fields);
        setInitial(saved);
        setDraft(saved);
      }
      setShown(false);
      toast.success("Saved");
    },
    onError: (error) => {
      if (isNoSession(error)) {
        sessionLost();
        return;
      }
      const fieldErrors = readFieldErrors(error);
      if (fieldErrors !== null) {
        const mapped: Record<string, string> = { ...fieldErrors };
        const next: DealerFieldProblems = mapped;
        setServer(next);
        return;
      }
      const { refusal } = refusalOf(error);
      toast.error(refusal.title, { description: refusal.message });
    },
  });

  const submit = useAsyncAction({
    action: () => submitApplicantApplication(applicant),
    logger: log,
    fn: "handleSubmitApplicantApplication",
    dataId: "CHNL-008",
    onSuccess: () => {
      refresh();
    },
    onError: (error) => {
      if (isNoSession(error)) {
        sessionLost();
        return;
      }
      const { refusal } = refusalOf(error);
      toast.error(refusal.title, { description: refusal.message });
      refresh();
    },
  });

  if (draft === null) {
    return (
      <Notice tone="warning">
        <p>Your details couldn&apos;t be read. Reload the page and verify your mobile again.</p>
      </Notice>
    );
  }

  const blocker = unsaved
    ? "Save your changes first."
    : view.missing.length > 0
      ? `Still needed: ${view.missing.map(missingLabel).join(", ")}.`
      : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold text-foreground">Dealer application</h1>
        <p className="text-sm text-muted-foreground">
          Fill in your firm&apos;s details and upload the documents, then submit. What you save is
          kept if you come back later.
        </p>
      </div>

      {view.status === "returned" ? (
        <Notice tone="warning">
          <p className="font-medium">Polysil sent your application back</p>
          {view.remark === null ? null : <p>{view.remark}</p>}
        </Notice>
      ) : null}

      <form
        noValidate
        aria-label="Your details"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          setShown(true);
          setServer({});
          if (Object.keys(local).length > 0 || !unsaved) return;
          void save.run();
        }}
      >
        <DealerFieldsEditor
          idPrefix="apply"
          draft={draft}
          onDraftChange={(next) => {
            setDraft(next);
            setServer({});
          }}
          problems={problems}
          gstinCheck={(gstin) => (
            <ApplicantGstinCheck token={token} session={session} gstin={gstin} />
          )}
        />
        <Button
          type="submit"
          className="self-start"
          disabled={!unsaved && save.state === "idle"}
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Save
        </Button>
      </form>

      <ApplicantDocuments
        token={token}
        session={session}
        documents={view.documents}
        onChanged={refresh}
        onSessionLost={sessionLost}
      />

      <div className="flex flex-col gap-2 border-t border-border pt-4">
        <Button
          className="self-start"
          disabled={blocker !== null && submit.state === "idle"}
          state={submit.state}
          loadingLabel="Submitting…"
          successLabel="Submitted"
          errorLabel="Not submitted"
          onClick={() => {
            void submit.run();
          }}
        >
          <Icon icon={SentIcon} />
          Submit the application
        </Button>
        {blocker === null ? (
          <p className="text-xs text-muted-foreground">
            Once submitted, Polysil reviews it. You can&apos;t change it until they reply.
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">{blocker}</p>
        )}
      </div>
    </div>
  );
}

/** "Check GSTIN": the GSTIN read from itself; the names are typed while there's no provider. */
function ApplicantGstinCheck({
  token,
  session,
  gstin,
}: {
  token: string;
  session: string;
  gstin: string;
}): React.JSX.Element {
  const [asked, setAsked] = useState(false);
  const lookup = useQuery({
    ...applicantGstinQueryOptions(token, session, gstin),
    enabled: asked,
  });
  if (!asked) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => {
          setAsked(true);
        }}
      >
        Check GSTIN
      </Button>
    );
  }
  if (lookup.isPending) {
    return (
      <p role="status" className="text-xs text-muted-foreground">
        Checking…
      </p>
    );
  }
  if (lookup.isError) {
    return (
      <p className="text-xs text-muted-foreground">Couldn&apos;t check it. Try again later.</p>
    );
  }
  const result = lookup.data;
  if (!result.valid) {
    return (
      <p role="alert" className="text-xs text-danger">
        {result.reason ?? "This GSTIN isn't valid."}
      </p>
    );
  }
  const name = result.tradeName ?? result.legalName;
  return (
    <p className="text-xs text-success">
      Valid GSTIN{result.pan === null ? "" : `, PAN ${result.pan}`}.
      {result.lookup === "found" && name !== null
        ? ` Registered as ${name}.`
        : " Type your firm's name as registered."}
    </p>
  );
}

function ApplicantDocuments({
  token,
  session,
  documents,
  onChanged,
  onSessionLost,
}: {
  token: string;
  session: string;
  documents: readonly ApplicantDocument[];
  onChanged: () => void;
  onSessionLost: () => void;
}): React.JSX.Element {
  const applicant = { token, session };
  const [docType, setDocType] = useState<ApplicantDocumentType>("pan_card");
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [inputKey, setInputKey] = useState(0);

  const upload = useAsyncAction({
    action: () => {
      if (file === null) throw new Error("No file chosen");
      return uploadApplicantDocument(applicant, {
        docType,
        name: name.trim() === "" ? null : name.trim(),
        file,
      });
    },
    logger: log,
    fn: "handleUploadApplicantDocument",
    dataId: "CHNL-008",
    onSuccess: () => {
      setFile(null);
      setName("");
      setInputKey((key) => key + 1);
      toast.success(`${APPLICANT_DOCUMENT_LABELS[docType] ?? "Document"} uploaded`);
      onChanged();
    },
    onError: (error) => {
      if (isNoSession(error)) {
        onSessionLost();
        return;
      }
      setProblem(
        isApiError(error) && error.code === "attachment_type"
          ? "JPEG, PNG, WebP, HEIC or PDF only."
          : isApiError(error) && error.status === 413
            ? "Up to 10 MB."
            : refusalOf(error).refusal.message,
      );
    },
  });

  return (
    <section aria-labelledby="apply-documents" className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h2 id="apply-documents" className="text-base font-semibold text-foreground">
          Documents
        </h2>
        <p className="text-sm text-muted-foreground">
          The GST certificate (if registered), PAN card and a cancelled cheque are needed. A shop
          photo or licence helps.
        </p>
      </div>
      {documents.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing uploaded yet.</p>
      ) : (
        <ul aria-label="Uploaded documents" className="flex flex-col divide-y divide-border">
          {documents.map((document) => (
            <DocumentRow
              key={document.id}
              document={document}
              onRemove={async () => {
                try {
                  await removeApplicantDocument(applicant, document.id);
                  onChanged();
                } catch (error: unknown) {
                  if (isNoSession(error)) onSessionLost();
                  else
                    toast.error("Couldn't remove it", {
                      description: refusalOf(error).refusal.message,
                    });
                }
              }}
            />
          ))}
        </ul>
      )}
      <form
        noValidate
        aria-label="Upload a document"
        className="flex flex-col gap-3 rounded-xl border border-border p-3"
        onSubmit={(event) => {
          event.preventDefault();
          setProblem(null);
          if (file === null) {
            setProblem("Choose a file.");
            return;
          }
          if (file.size > MAX_BYTES) {
            setProblem("Up to 10 MB.");
            return;
          }
          if (docType === "other" && name.trim() === "") {
            setProblem("Name the document.");
            return;
          }
          void upload.run();
        }}
      >
        <Field>
          <FieldLabel htmlFor="apply-doc-type">Document</FieldLabel>
          <Select
            items={APPLICANT_DOCUMENT_TYPES.map((value) => ({
              value,
              label: APPLICANT_DOCUMENT_LABELS[value] ?? value,
            }))}
            value={docType}
            onValueChange={(next) => {
              const found = APPLICANT_DOCUMENT_TYPES.find((value) => value === next);
              if (found !== undefined) setDocType(found);
            }}
          >
            <SelectTrigger id="apply-doc-type" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {APPLICANT_DOCUMENT_TYPES.map((value) => (
                <SelectItem key={value} value={value}>
                  {APPLICANT_DOCUMENT_LABELS[value] ?? value}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        {docType === "other" ? (
          <Field>
            <FieldLabel htmlFor="apply-doc-name">Name</FieldLabel>
            <Input
              id="apply-doc-name"
              maxLength={80}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </Field>
        ) : null}
        <Field data-invalid={problem === null ? undefined : true}>
          <FieldLabel htmlFor="apply-doc-file">File</FieldLabel>
          <Input
            key={inputKey}
            id="apply-doc-file"
            type="file"
            accept={ACCEPT}
            aria-invalid={problem === null ? undefined : true}
            aria-describedby={problem === null ? "apply-doc-file-hint" : "apply-doc-file-error"}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setProblem(null);
            }}
          />
          {problem === null ? (
            <FieldDescription id="apply-doc-file-hint">
              A photo or PDF, up to 10 MB.
            </FieldDescription>
          ) : null}
          <FieldError id="apply-doc-file-error">{problem ?? undefined}</FieldError>
        </Field>
        <Button
          type="submit"
          variant="outline"
          className="self-start"
          state={upload.state}
          loadingLabel="Uploading…"
          successLabel="Uploaded"
          errorLabel="Not uploaded"
        >
          <Icon icon={Upload04Icon} />
          Upload
        </Button>
      </form>
    </section>
  );
}

function DocumentRow({
  document,
  onRemove,
}: {
  document: ApplicantDocument;
  onRemove: () => Promise<void>;
}): React.JSX.Element {
  const label = document.name ?? APPLICANT_DOCUMENT_LABELS[document.docType] ?? document.docType;
  return (
    <li className="flex min-h-11 items-center gap-2 py-2">
      <Icon icon={File01Icon} className="text-muted-foreground" />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-sm text-foreground">{label}</span>
        <span className="truncate text-xs text-muted-foreground">{document.filename}</span>
      </span>
      {document.mine ? (
        <Button
          variant="ghost"
          size="icon-md"
          aria-label={`Remove ${label}`}
          onClick={() => {
            void onRemove();
          }}
        >
          <Icon icon={Delete02Icon} />
        </Button>
      ) : null}
    </li>
  );
}
