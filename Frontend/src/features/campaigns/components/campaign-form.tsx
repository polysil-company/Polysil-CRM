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
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useCreateCampaign, usePatchCampaign } from "@/features/campaigns/api/campaigns.mutations";
import {
  CAMPAIGN_TYPES,
  type Campaign,
  type CampaignCreateRequest,
  type CampaignType,
} from "@/features/campaigns/api/campaigns.schemas";
import { CAMPAIGN_TYPE_LABELS } from "@/features/campaigns/lib/campaign-labels";
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/campaigns/components/campaign-form.tsx",
  dataId: "MKT-005",
});

const TYPE_ITEMS = CAMPAIGN_TYPES.map((value) => ({ value, label: CAMPAIGN_TYPE_LABELS[value] }));

interface Draft {
  readonly name: string;
  readonly type: CampaignType | null;
  readonly territory: TerritoryChoice | null;
  readonly start: string;
  readonly end: string;
  readonly costPlanned: string;
  readonly costActual: string;
  readonly description: string;
}

type FieldName = keyof Draft;

/** The backend's field names onto the form's. */
const WIRE_FIELDS: Readonly<Record<string, FieldName>> = {
  name: "name",
  type: "type",
  territory_id: "territory",
  start_date: "start",
  end_date: "end",
  cost_planned: "costPlanned",
  cost_actual: "costActual",
  description: "description",
};

const RUPEES = /^\d+(\.\d{1,2})?$/;

function problemsOf(draft: Draft): Partial<Record<FieldName, string>> {
  const problems: Partial<Record<FieldName, string>> = {};
  if (draft.name.trim() === "") problems.name = "Name it, like Krishi Mela Rajkot 2026.";
  if (draft.type === null) problems.type = "Choose what kind of campaign it is.";
  if (draft.start === "") problems.start = "Pick the day it starts.";
  if (draft.end !== "" && draft.start !== "" && draft.end < draft.start) {
    problems.end = "Not before the start.";
  }
  if (draft.costPlanned.trim() !== "" && !RUPEES.test(draft.costPlanned.trim())) {
    problems.costPlanned = "Rupees, like 150000.";
  }
  if (draft.costActual.trim() !== "" && !RUPEES.test(draft.costActual.trim())) {
    problems.costActual = "Rupees, like 148500.";
  }
  return problems;
}

function draftOf(campaign: Campaign | null): Draft {
  return {
    name: campaign?.name ?? "",
    type: campaign?.type ?? null,
    territory: campaign?.territory ?? null,
    start: campaign?.startDate ?? todayInIndia(),
    end: campaign?.endDate ?? "",
    costPlanned:
      campaign?.costPlanned === null || campaign === null
        ? ""
        : String(Number(campaign.costPlanned)),
    costActual: campaign?.costActual == null ? "" : String(Number(campaign.costActual)),
    description: campaign?.description ?? "",
  };
}

/**
 * MKT-005 · Add a campaign or change one: its name (unique, case ignored), kind, where it is held,
 * its dates, planned and actual cost, and a description. The cost fields show only to those who
 * may see cost; a change leaves what they can't see alone.
 */
export function CampaignForm({
  campaign,
  onClose,
}: {
  campaign: Campaign | null;
  onClose: () => void;
}): React.JSX.Element {
  const adding = campaign === null;
  // Cost comes back null without campaigns.view: someone who can't see it can't set it either.
  const seesCost = adding || campaign.costPlanned !== null;
  const create = useCreateCampaign();
  const patch = usePatchCampaign();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const [draft, setDraft] = useState<Draft>(() => draftOf(campaign));
  const [shown, setShown] = useState(false);
  const [serverProblems, setServerProblems] = useState<Partial<Record<FieldName, string>>>({});
  const [refusal, setRefusal] = useState<string | null>(null);
  const problems = { ...(shown ? problemsOf(draft) : {}), ...serverProblems };

  const set = (next: Partial<Draft>): void => {
    setDraft({ ...draft, ...next });
    setServerProblems({});
  };

  const submit = useAsyncAction({
    action: () => {
      const body: CampaignCreateRequest = {
        name: draft.name.trim(),
        type: draft.type ?? "other",
        territory_id: draft.territory?.id ?? null,
        start_date: draft.start,
        end_date: draft.end === "" ? null : draft.end,
        cost_planned: draft.costPlanned.trim() === "" ? "0" : draft.costPlanned.trim(),
        cost_actual: draft.costActual.trim() === "" ? null : draft.costActual.trim(),
        description: draft.description.trim() === "" ? null : draft.description.trim(),
      };
      if (campaign === null) {
        return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
      }
      const { cost_planned: costPlanned, cost_actual: costActual, ...rest } = body;
      const patchBody = seesCost
        ? { ...rest, cost_planned: costPlanned, cost_actual: costActual }
        : rest;
      return patch.mutateAsync({
        campaignId: campaign.id,
        body: patchBody,
        idempotencyKey: idempotency.keyFor({ id: campaign.id, ...patchBody }),
      });
    },
    logger: log,
    fn: adding ? "handleCreateCampaign" : "handlePatchCampaign",
    dataId: "MKT-005",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(adding ? `${saved.name} added` : `${saved.name} saved`, {
        description: adding ? "Staff can now pick it on a lead or a QR code." : undefined,
      });
      closeSoon();
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "campaign_name_taken") {
        setServerProblems({ name: "Another campaign has this name." });
        return;
      }
      const mapped: Partial<Record<FieldName, string>> = {};
      for (const [key, reason] of Object.entries(readFieldErrors(error) ?? {})) {
        const name = WIRE_FIELDS[key];
        if (name !== undefined) mapped[name] = reason;
      }
      if (Object.keys(mapped).length > 0) {
        setServerProblems(mapped);
        return;
      }
      setRefusal(toUserFacingError(error).title);
    },
  });

  const aria = (
    name: FieldName,
    help?: boolean,
  ): {
    "aria-invalid": true | undefined;
    "aria-describedby": string | undefined;
  } => {
    const ids = [
      problems[name] === undefined ? null : `campaign-${name}-error`,
      help === true ? `campaign-${name}-help` : null,
    ].filter((value) => value !== null);
    return {
      "aria-invalid": problems[name] === undefined ? undefined : true,
      "aria-describedby": ids.length === 0 ? undefined : ids.join(" "),
    };
  };
  const errorOf = (name: FieldName): React.JSX.Element | null =>
    problems[name] === undefined ? null : (
      <FieldError id={`campaign-${name}-error`}>{problems[name]}</FieldError>
    );

  return (
    <form
      noValidate
      aria-label={adding ? "New campaign" : `Change ${campaign.name}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (Object.keys(problemsOf(draft)).length > 0) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>{adding ? "New campaign" : `Change ${campaign.name}`}</DialogTitle>
        <DialogDescription>
          Staff pick it on a lead or a QR code, and Reports count its leads and sales.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="grid gap-4 sm:grid-cols-2">
        <Field
          className="sm:col-span-2"
          data-invalid={problems.name === undefined ? undefined : true}
        >
          <FieldLabel htmlFor="campaign-name">Name</FieldLabel>
          <Input
            id="campaign-name"
            autoComplete="off"
            maxLength={160}
            value={draft.name}
            {...aria("name")}
            onChange={(event) => {
              set({ name: event.target.value });
            }}
          />
          {errorOf("name")}
        </Field>
        <Field data-invalid={problems.type === undefined ? undefined : true}>
          <FieldLabel htmlFor="campaign-type">Kind</FieldLabel>
          <Select
            items={TYPE_ITEMS}
            value={draft.type}
            onValueChange={(next) => {
              set({ type: CAMPAIGN_TYPES.find((value) => value === next) ?? null });
            }}
          >
            <SelectTrigger id="campaign-type" {...aria("type")}>
              <SelectValue placeholder="Choose a kind" />
            </SelectTrigger>
            <SelectContent>
              {TYPE_ITEMS.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {errorOf("type")}
        </Field>
        <Field data-invalid={problems.territory === undefined ? undefined : true}>
          <FieldLabel htmlFor="campaign-territory">
            Where
            <span className="font-normal text-subtle-foreground">(optional)</span>
          </FieldLabel>
          <TerritoryPicker
            id="campaign-territory"
            value={draft.territory}
            placeholder="Search a state, district or taluka"
            onValueChange={(territory) => {
              set({ territory });
            }}
            {...aria("territory")}
          />
          {errorOf("territory")}
        </Field>
        <Field data-invalid={problems.start === undefined ? undefined : true}>
          <FieldLabel htmlFor="campaign-start">Starts</FieldLabel>
          <Input
            id="campaign-start"
            type="date"
            value={draft.start}
            {...aria("start")}
            onChange={(event) => {
              set({ start: event.target.value });
            }}
          />
          {errorOf("start")}
        </Field>
        <Field data-invalid={problems.end === undefined ? undefined : true}>
          <FieldLabel htmlFor="campaign-end">
            Ends
            <span className="font-normal text-subtle-foreground">(optional)</span>
          </FieldLabel>
          <Input
            id="campaign-end"
            type="date"
            min={draft.start === "" ? undefined : draft.start}
            value={draft.end}
            {...aria("end", true)}
            onChange={(event) => {
              set({ end: event.target.value });
            }}
          />
          <FieldDescription id="campaign-end-help">Empty: a one-day campaign.</FieldDescription>
          {errorOf("end")}
        </Field>
        {seesCost ? (
          <>
            <Field data-invalid={problems.costPlanned === undefined ? undefined : true}>
              <FieldLabel htmlFor="campaign-cost-planned">Planned cost</FieldLabel>
              <InputGroup>
                <InputGroupAddon>₹</InputGroupAddon>
                <InputGroupInput
                  id="campaign-cost-planned"
                  inputMode="decimal"
                  autoComplete="off"
                  className="tabular-nums"
                  placeholder="0"
                  value={draft.costPlanned}
                  {...aria("costPlanned")}
                  onChange={(event) => {
                    set({ costPlanned: event.target.value });
                  }}
                />
              </InputGroup>
              {errorOf("costPlanned")}
            </Field>
            <Field data-invalid={problems.costActual === undefined ? undefined : true}>
              <FieldLabel htmlFor="campaign-cost-actual">
                Actual cost
                <span className="font-normal text-subtle-foreground">(once known)</span>
              </FieldLabel>
              <InputGroup>
                <InputGroupAddon>₹</InputGroupAddon>
                <InputGroupInput
                  id="campaign-cost-actual"
                  inputMode="decimal"
                  autoComplete="off"
                  className="tabular-nums"
                  value={draft.costActual}
                  {...aria("costActual")}
                  onChange={(event) => {
                    set({ costActual: event.target.value });
                  }}
                />
              </InputGroup>
              {errorOf("costActual")}
            </Field>
          </>
        ) : null}
        <Field
          className="sm:col-span-2"
          data-invalid={problems.description === undefined ? undefined : true}
        >
          <FieldLabel htmlFor="campaign-description">
            Description
            <span className="font-normal text-subtle-foreground">(optional)</span>
          </FieldLabel>
          <Textarea
            id="campaign-description"
            rows={2}
            maxLength={2000}
            value={draft.description}
            {...aria("description")}
            onChange={(event) => {
              set({ description: event.target.value });
            }}
          />
          {errorOf("description")}
        </Field>
        {refusal === null ? null : (
          <p
            role="alert"
            className="rounded-md bg-danger-soft p-3 text-sm text-danger sm:col-span-2"
          >
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          {adding ? "Add campaign" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
