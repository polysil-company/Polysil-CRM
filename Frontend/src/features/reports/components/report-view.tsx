"use client";

import { ArrowLeft01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { createParser, parseAsArrayOf, useQueryStates } from "nuqs";
import type * as React from "react";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { FilterPill, SingleFilterPill } from "@/components/patterns/filter-pill";
import { Notice } from "@/components/patterns/notice";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { LeadAreaFilter } from "@/features/leads/components/lead-area-filter";
import { downloadReport } from "@/features/reports/api/reports.api";
import {
  REPORT_MAX_DAYS,
  REPORT_MAX_ROLES,
  REPORT_MAX_TERRITORIES,
  type ReportName,
  type ReportParams,
} from "@/features/reports/api/reports.schemas";
import { REPORTS } from "@/features/reports/lib/report-catalogue";
import { staffAssigneesQueryOptions } from "@/features/tasks/api/tasks.queries";
import { roleListQueryOptions } from "@/features/users/api/users.queries";
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

const parseAsRole = createParser({
  parse: (value: string) => (/^[a-z_]{1,40}$/.test(value) ? value : null),
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
  /** FS-082 · One person's team; never with `owner`. */
  team: parseAsId,
  roles: parseAsArrayOf(parseAsRole).withDefault([]),
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
    // The backend refuses a person and a team together; the person wins.
    teamOf: entry.team && (values.owner === null || !entry.owner) ? values.team : null,
    roles: entry.team ? [...new Set(values.roles)].slice(0, REPORT_MAX_ROLES) : [],
    groupBy,
  };
  const problem = windowProblem(params.from, params.to);
  const filtered =
    params.from !== null ||
    params.to !== null ||
    params.territories.length > 0 ||
    params.owner !== null ||
    params.teamOf !== null ||
    params.roles.length > 0 ||
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
              void setValues(owner === null ? { owner } : { owner, team: null });
            }}
          />
        ) : null}
        {entry.team ? (
          <>
            <PersonFilter
              label="Team"
              selected={params.teamOf}
              onChange={(team) => {
                void setValues(team === null ? { team } : { team, owner: null });
              }}
            />
            <RolesFilter
              selected={params.roles}
              onChange={(roles) => {
                void setValues({ roles: roles.length === 0 ? null : roles });
              }}
            />
          </>
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
              void setValues({
                from: null,
                to: null,
                area: null,
                owner: null,
                team: null,
                roles: null,
                by: null,
              });
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

/**
 * One person: you, then the staff below you (GET /tasks/assignees). As "Team" (FS-082), that
 * person and everyone below them on the org chart.
 */
function PersonFilter({
  label = "Person",
  selected,
  onChange,
}: {
  label?: string;
  selected: string | null;
  onChange: (owner: string | null) => void;
}): React.JSX.Element {
  const people = useQuery(staffAssigneesQueryOptions());
  return (
    <SingleFilterPill
      label={label}
      options={(people.data ?? []).map((person) => ({ value: person.id, label: person.name }))}
      selected={selected}
      emptyMessage={people.isPending ? "Loading people…" : "The people couldn't be loaded."}
      onChange={onChange}
    />
  );
}

/** FS-082 · Only people holding one of these roles now: the staff roles (GET /lookups/roles). */
function RolesFilter({
  selected,
  onChange,
}: {
  selected: readonly string[];
  onChange: (roles: string[]) => void;
}): React.JSX.Element {
  const roles = useQuery(roleListQueryOptions());
  return (
    <FilterPill
      label="Roles"
      options={(roles.data ?? [])
        .filter((role) => !role.portal)
        .map((role) => ({ value: role.code, label: role.name }))}
      selected={selected}
      emptyMessage={roles.isPending ? "Loading roles…" : "The roles couldn't be loaded."}
      onChange={(next) => {
        onChange(next.slice(0, REPORT_MAX_ROLES));
      }}
    />
  );
}
