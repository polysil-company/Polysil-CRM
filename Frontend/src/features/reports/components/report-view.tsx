"use client";

import { ArrowLeft01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { createParser, parseAsArrayOf, useQueryStates } from "nuqs";
import type * as React from "react";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { SingleFilterPill } from "@/components/patterns/filter-pill";
import { Notice } from "@/components/patterns/notice";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { LeadAreaFilter } from "@/features/leads/components/lead-area-filter";
import { downloadReport } from "@/features/reports/api/reports.api";
import {
  REPORT_MAX_DAYS,
  REPORT_MAX_TERRITORIES,
  type ReportName,
  type ReportParams,
} from "@/features/reports/api/reports.schemas";
import { REPORTS } from "@/features/reports/lib/report-catalogue";
import { taskAssigneesQueryOptions } from "@/features/tasks/api/tasks.queries";
import { createLogger } from "@/lib/logger";

import { ReportBody } from "./report-bodies";

const log = createLogger({
  file: "features/reports/components/report-view.tsx",
  dataId: "RPT-002",
});

const DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const ID_PATTERN = /^[\w-]{1,64}$/;

const parseAsDay = createParser({
  parse: (value: string) => (DAY_PATTERN.test(value) ? value : null),
  serialize: (value: string) => value,
});

const parseAsId = createParser({
  parse: (value: string) => (ID_PATTERN.test(value) ? value : null),
  serialize: (value: string) => value,
});

const parseAsGroup = createParser({
  parse: (value: string) => (/^[a-z_]{1,32}$/.test(value) ? value : null),
  serialize: (value: string) => value,
});

/** Filters live in the URL, so a report can be bookmarked or sent to a colleague. */
const reportSearchParams = {
  from: parseAsDay,
  to: parseAsDay,
  area: parseAsArrayOf(parseAsId).withDefault([]),
  owner: parseAsId,
  by: parseAsGroup,
};

const DAY_MS = 24 * 60 * 60 * 1000;

/** Why a window won't do, before asking: backwards, or longer than a year. */
function windowProblem(from: string | null, to: string | null): string | null {
  if (from === null || to === null) return null;
  if (from > to) return "The window starts after it ends. Pick a start before the end.";
  const days = (Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS + 1;
  return days > REPORT_MAX_DAYS ? "A report covers a year at most. Shorten the window." : null;
}

/**
 * RPT-002 · One report: its window, areas, person and grouping (each only where the report
 * takes it), the figures, and the same rows as Excel.
 */
export function ReportView({ name }: { name: ReportName }): React.JSX.Element {
  const entry = REPORTS[name];
  const [values, setValues] = useQueryStates(reportSearchParams);
  const groups = entry.groups;
  const groupBy =
    values.by !== null && groups.some((group) => group.value === values.by) ? values.by : null;
  const params: ReportParams = {
    from: entry.dates ? values.from : null,
    to: entry.dates ? values.to : null,
    territories: entry.territory ? [...new Set(values.area)].slice(0, REPORT_MAX_TERRITORIES) : [],
    owner: entry.owner ? values.owner : null,
    groupBy,
  };
  const problem = windowProblem(params.from, params.to);
  const filtered =
    params.from !== null ||
    params.to !== null ||
    params.territories.length > 0 ||
    params.owner !== null ||
    params.groupBy !== null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Link
          href="/reports"
          className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          <Icon icon={ArrowLeft01Icon} />
          All reports
        </Link>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="flex flex-col gap-0.5">
            <h2 className="text-lg font-semibold text-foreground">{entry.title}</h2>
            <p className="max-w-prose text-sm text-muted-foreground">{entry.description}</p>
          </div>
          {problem === null ? (
            <DownloadExcelButton
              download={() => downloadReport(name, params)}
              fallbackName={`report-${name}.xlsx`}
              what={`the ${entry.title.toLowerCase()} report`}
              logger={log}
              dataId="RPT-002"
            />
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {entry.dates ? (
          <DayRange
            from={values.from}
            to={values.to}
            onChange={(range) => {
              void setValues(range);
            }}
          />
        ) : null}
        {entry.territory ? (
          <LeadAreaFilter
            selected={params.territories}
            onChange={(area) => {
              void setValues({ area: area.length === 0 ? null : area });
            }}
          />
        ) : null}
        {entry.owner ? (
          <PersonFilter
            selected={params.owner}
            onChange={(owner) => {
              void setValues({ owner });
            }}
          />
        ) : null}
        {groups.length > 0 ? (
          <SingleFilterPill
            label="By"
            options={groups}
            selected={groupBy ?? groups[0]?.value ?? null}
            onChange={(by) => {
              void setValues({ by: by === groups[0]?.value ? null : by });
            }}
          />
        ) : null}
        {filtered ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              void setValues({ from: null, to: null, area: null, owner: null, by: null });
            }}
          >
            Reset filters
          </Button>
        ) : null}
      </div>

      {problem === null ? (
        <ReportBody name={name} params={params} />
      ) : (
        <Notice tone="warning">{problem}</Notice>
      )}
    </div>
  );
}

function DayRange({
  from,
  to,
  onChange,
}: {
  from: string | null;
  to: string | null;
  onChange: (range: { from?: string | null; to?: string | null }) => void;
}): React.JSX.Element {
  return (
    <div role="group" aria-label="Window" className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        From
        <Input
          type="date"
          value={from ?? ""}
          max={to ?? undefined}
          className="h-control-sm w-auto"
          onChange={(event) => {
            onChange({ from: event.target.value === "" ? null : event.target.value });
          }}
        />
      </label>
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        to
        <Input
          type="date"
          value={to ?? ""}
          min={from ?? undefined}
          className="h-control-sm w-auto"
          onChange={(event) => {
            onChange({ to: event.target.value === "" ? null : event.target.value });
          }}
        />
      </label>
      {from === null && to === null ? (
        <span className="text-xs text-muted-foreground">The last 30 days</span>
      ) : null}
    </div>
  );
}

/** One person: you, then the staff below you (GET /tasks/assignees). */
function PersonFilter({
  selected,
  onChange,
}: {
  selected: string | null;
  onChange: (owner: string | null) => void;
}): React.JSX.Element {
  const people = useQuery(taskAssigneesQueryOptions());
  return (
    <SingleFilterPill
      label="Person"
      options={(people.data ?? []).map((person) => ({ value: person.id, label: person.name }))}
      selected={selected}
      emptyMessage={people.isPending ? "Loading people…" : "The people couldn't be loaded."}
      onChange={onChange}
    />
  );
}
