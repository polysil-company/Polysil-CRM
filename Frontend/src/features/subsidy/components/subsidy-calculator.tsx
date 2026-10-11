"use client";

import { Add01Icon, Calculator01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Notice } from "@/components/patterns/notice";
import { QueryView } from "@/components/patterns/query-view";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  subsidyCategoriesQueryOptions,
  subsidyConfigQueryOptions,
  subsidyCropsQueryOptions,
} from "@/features/subsidy/api/subsidy.queries";
import {
  SYSTEM_TYPES,
  type SubsidyCrop,
  type SystemConfig,
  type SystemType,
} from "@/features/subsidy/api/subsidy.schemas";
import { useSubsidyCalculation } from "@/features/subsidy/hooks/use-subsidy-calculation";
import {
  emptyCrop,
  emptyDraft,
  type CalculatorDraft,
  type DraftProblems,
} from "@/features/subsidy/lib/calculator-draft";
import { SYSTEM_LABELS } from "@/features/subsidy/lib/subsidy-labels";

import { CropBlockCard, HeadUnitCard, QuotationCostsCard } from "./calculator-inputs";
import { CalculatorResults, CalculatorResultsSkeleton } from "./calculator-results";

type Drafts = Readonly<Record<SystemType, CalculatorDraft>>;

/** The paths an input on screen shows; anything else is listed above the figures. */
const PLACED_PATH =
  /^(crops\[\d+\]\.(crop|inter_crop|area|lateral_spacing|crop_spacing|lines\[\d+\]\.(description|uom|rate|qty))|head_lines\[\d+\]\.(description|uom|rate|qty)|sump\.rate_per_ha|group_total_area|installation_rate_per_ha|nozzle)$/;

const UNPLACED_NAMES: Readonly<Record<string, string>> = {
  crops: "Crop blocks",
  scheme: "Scheme",
  system_type: "System",
  as_of: "Date",
};

function unplacedProblems(problems: DraftProblems): string[] {
  return Object.entries(problems)
    .filter(([path]) => !PLACED_PATH.test(path))
    .map(([path, problem]) => `${UNPLACED_NAMES[path] ?? path}: ${problem}`);
}

/**
 * SUBS-002 · The subsidy calculator. Drip, Mini Sprinkler and Sprinkler are three screens, each
 * shaped by `GET /subsidy/config` rather than hard-coded: how many crop blocks, whether there is
 * a head unit or a group, which areas Sprinkler takes. Each keeps its own inputs while the
 * designer moves between them. Nothing is saved.
 */
export function SubsidyCalculator(): React.JSX.Element {
  const [systemType, setSystemType] = useQueryState(
    "system",
    parseAsStringLiteral(SYSTEM_TYPES).withDefault("drip"),
  );
  const config = useQuery(subsidyConfigQueryOptions());
  const crops = useQuery(subsidyCropsQueryOptions());
  const [drafts, setDrafts] = useState<Drafts>(() => ({
    drip: emptyDraft("drip"),
    mini_sprinkler: emptyDraft("mini_sprinkler"),
    sprinkler: emptyDraft("sprinkler"),
  }));

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-prose text-sm text-muted-foreground">
        Enter the design as you would on the scheme&apos;s sheet. The figures come from the
        scheme&apos;s masters in force today and update as you type.
      </p>
      <QueryView
        query={config}
        pending={<SubsidyCalculatorSkeleton />}
        isEmpty={(data) => data.systems.length === 0}
        empty={
          <EmptyState
            icon={Calculator01Icon}
            title="No subsidy tables in force"
            description="The scheme's masters for today haven't been loaded. Ask an administrator."
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => (
          <Tabs
            value={systemType}
            onValueChange={(value: SystemType) => {
              void setSystemType(value);
            }}
          >
            <TabsList variant="segmented" aria-label="System">
              {SYSTEM_TYPES.map((type) => (
                <TabsTrigger
                  key={type}
                  value={type}
                  variant="segmented"
                  disabled={!data.systems.some((system) => system.systemType === type)}
                >
                  {SYSTEM_LABELS[type]}
                </TabsTrigger>
              ))}
            </TabsList>
            {SYSTEM_TYPES.map((type) => {
              const system = data.systems.find((row) => row.systemType === type);
              return (
                <TabsContent key={type} value={type}>
                  {system === undefined ? null : (
                    <SystemCalculator
                      system={system}
                      parameters={data.parameters}
                      catalogue={crops.data ?? []}
                      cropsFailed={crops.isError}
                      onRetryCrops={() => {
                        void crops.refetch();
                      }}
                      draft={drafts[type]}
                      onDraftChange={(next) => {
                        setDrafts((current) => ({ ...current, [type]: next }));
                      }}
                    />
                  )}
                </TabsContent>
              );
            })}
          </Tabs>
        )}
      </QueryView>
    </div>
  );
}

interface SystemCalculatorProps {
  system: SystemConfig;
  parameters: Readonly<Record<string, string>>;
  catalogue: readonly SubsidyCrop[];
  cropsFailed: boolean;
  onRetryCrops: () => void;
  draft: CalculatorDraft;
  onDraftChange: (next: CalculatorDraft) => void;
}

/** SUBS-002 · One system's inputs beside its figures. */
function SystemCalculator({
  system,
  parameters,
  catalogue,
  cropsFailed,
  onRetryCrops,
  draft,
  onDraftChange,
}: SystemCalculatorProps): React.JSX.Element {
  const calculation = useSubsidyCalculation(draft, system);
  const categories = useQuery(subsidyCategoriesQueryOptions(system.systemType));
  const { problems, plan } = calculation;
  const blocks = draft.crops.slice(0, system.cropCountMax);
  const label = SYSTEM_LABELS[system.systemType];

  const waitingFor =
    plan.missing.length > 0
      ? system.systemType === "sprinkler"
        ? "Choose the area and enter the lateral spacing to see the subsidy."
        : "Enter each crop's area and lateral spacing to see the subsidy."
      : Object.keys(problems).length > 0
        ? "Correct the marked fields to see the subsidy."
        : null;

  return (
    <div className="grid gap-6 xl:grid-cols-2 xl:items-start">
      <form
        aria-label={`${label} inputs`}
        noValidate
        className="flex min-w-0 flex-col gap-4"
        onSubmit={(event) => {
          // Nothing to submit: the figures follow the inputs.
          event.preventDefault();
        }}
      >
        {cropsFailed ? (
          <Notice tone="danger">
            <p>The crop list couldn&apos;t be loaded, so crops can&apos;t be chosen yet.</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="self-start"
              onClick={onRetryCrops}
            >
              Try again
            </Button>
          </Notice>
        ) : null}
        {blocks.map((crop, index) => (
          <CropBlockCard
            key={crop.key}
            crop={crop}
            index={index}
            system={system}
            catalogue={catalogue}
            problems={problems}
            onChange={(next) => {
              onDraftChange({
                ...draft,
                crops: draft.crops.map((item) => (item.key === next.key ? next : item)),
              });
            }}
            onRemove={
              index === 0
                ? undefined
                : () => {
                    onDraftChange({
                      ...draft,
                      crops: draft.crops.filter((item) => item.key !== crop.key),
                    });
                  }
            }
          />
        ))}
        {blocks.length < system.cropCountMax ? (
          <Button
            type="button"
            variant="outline"
            className="self-start"
            onClick={() => {
              onDraftChange({ ...draft, crops: [...blocks, emptyCrop()] });
            }}
          >
            <Icon icon={Add01Icon} />
            Add a crop block
          </Button>
        ) : null}
        {system.hasHeadUnit ? (
          <HeadUnitCard draft={draft} problems={problems} onChange={onDraftChange} />
        ) : null}
        <QuotationCostsCard
          draft={draft}
          system={system}
          problems={problems}
          onChange={onDraftChange}
        />
      </form>

      <CalculatorResults
        system={system}
        parameters={parameters}
        result={calculation.result}
        upToDate={calculation.upToDate}
        calculating={calculation.calculating}
        waitingFor={waitingFor}
        categories={categories.data ?? null}
        unplaced={unplacedProblems(problems)}
        failed={
          calculation.failed ? (
            <ErrorState
              error={calculation.query.error}
              onRetry={() => {
                void calculation.query.refetch();
              }}
            />
          ) : null
        }
      />
    </div>
  );
}

export function SubsidyCalculatorSkeleton(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-4" aria-hidden>
      <Skeleton className="h-control-sm w-72 max-w-full rounded-md" />
      <div className="grid gap-6 pt-4 xl:grid-cols-2">
        <div className="flex flex-col gap-4">
          <Skeleton className="h-96 w-full rounded-xl" />
          <Skeleton className="h-48 w-full rounded-xl" />
        </div>
        <CalculatorResultsSkeleton />
      </div>
    </div>
  );
}
