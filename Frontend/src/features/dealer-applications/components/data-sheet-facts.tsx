import type * as React from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { DataSheet } from "@/features/dealer-applications/api/data-sheet.schemas";
import {
  AREA_UNIT_SHORT,
  INSTALLATION_SCOPE_LABELS,
} from "@/features/dealer-applications/lib/dealer-application-labels";
import { EMPTY_VALUE, formatFullDate, formatNumber } from "@/lib/format";

/**
 * CHNL-007 · The data sheet on an application's page (FS-071): the business facts, working
 * capital, premises and vehicles, people, and installations done before. A part with nothing
 * filled in says so in one line rather than showing a table of dashes.
 */
export function DataSheetFacts({ sheet }: { sheet: DataSheet }): React.JSX.Element {
  const area = (value: string | null): string =>
    value === null
      ? EMPTY_VALUE
      : `${formatNumber(Number(value))} ${AREA_UNIT_SHORT[sheet.areaUnit]}`;
  const count = (value: number | null): string =>
    value === null ? EMPTY_VALUE : formatNumber(value);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Data sheet</CardTitle>
          <CardDescription>
            What the printed application form asks about the business.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
          <Fact label="Telephone">{sheet.telephone ?? EMPTY_VALUE}</Fact>
          <Fact label="Established on">
            {sheet.establishedOn === null ? EMPTY_VALUE : formatFullDate(sheet.establishedOn)}
          </Fact>
          <Fact label="Place of appointment">{sheet.appointmentPlace ?? EMPTY_VALUE}</Fact>
          <Fact label="Bank">
            {[sheet.bankName, sheet.bankBranch].filter((part) => part !== null).join(", ") ||
              EMPTY_VALUE}
          </Fact>
          <Fact label="Branch address">{sheet.bankAddress ?? EMPTY_VALUE}</Fact>
        </dl>

        <section aria-labelledby="data-sheet-capital" className="flex flex-col gap-2">
          <h4 id="data-sheet-capital" className="text-sm font-semibold text-foreground">
            Working capital
          </h4>
          {sheet.workingCapital.length === 0 && sheet.otherSourcesLakhs === null ? (
            <p className="text-sm text-muted-foreground">Not given.</p>
          ) : (
            <ul className="flex flex-col gap-1 text-sm text-foreground">
              {sheet.workingCapital.map((row, index) => (
                // Rows have no id; their order is the applicant's.
                <li key={index} className="flex justify-between gap-4">
                  <span className="min-w-0 wrap-break-word">{row.facility}</span>
                  <span className="tabular-nums">{row.amountLakhs} lakhs</span>
                </li>
              ))}
              {sheet.otherSourcesLakhs === null ? null : (
                <li className="flex justify-between gap-4">
                  <span>Other sources</span>
                  <span className="tabular-nums">{sheet.otherSourcesLakhs} lakhs</span>
                </li>
              )}
              {sheet.workingCapitalTotalLakhs === null ? null : (
                <li className="flex justify-between gap-4 border-t border-border pt-1 font-medium">
                  <span>Total</span>
                  <span className="tabular-nums">{sheet.workingCapitalTotalLakhs} lakhs</span>
                </li>
              )}
            </ul>
          )}
        </section>

        <section aria-labelledby="data-sheet-premises" className="flex flex-col gap-2">
          <h4 id="data-sheet-premises" className="text-sm font-semibold text-foreground">
            Premises and vehicles
          </h4>
          <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
            <Fact label="Office">{area(sheet.officeArea)}</Fact>
            <Fact label="Godown">{area(sheet.godownArea)}</Fact>
            <Fact label="Two-wheelers">{count(sheet.twoWheelers)}</Fact>
            <Fact label="Cars">{count(sheet.cars)}</Fact>
            <Fact label="Other vehicles">{sheet.otherVehicles ?? EMPTY_VALUE}</Fact>
          </dl>
        </section>

        <section aria-labelledby="data-sheet-people" className="flex flex-col gap-2">
          <h4 id="data-sheet-people" className="text-sm font-semibold text-foreground">
            People
          </h4>
          <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
            <Fact label="Sales executives">{count(sheet.salesExecutives)}</Fact>
            <Fact label="Technicians">{count(sheet.technicians)}</Fact>
          </dl>
          {sheet.manpower.length === 0 ? null : (
            <ul className="flex flex-col gap-1 text-sm text-foreground">
              {sheet.manpower.map((row, index) => (
                <li key={index} className="wrap-break-word">
                  <span className="font-medium">
                    {formatNumber(row.people)} × {row.category}
                  </span>
                  {[
                    row.qualification,
                    row.workType,
                    row.experienceYears === null
                      ? null
                      : `${formatNumber(row.experienceYears)} years' experience`,
                  ]
                    .filter((part) => part !== null)
                    .map((part) => ` · ${part}`)
                    .join("")}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="data-sheet-installations" className="flex flex-col gap-2">
          <h4 id="data-sheet-installations" className="text-sm font-semibold text-foreground">
            Installations done before
          </h4>
          {sheet.previousInstallations.length === 0 ? (
            <p className="text-sm text-muted-foreground">None given.</p>
          ) : (
            <ul className="flex flex-col gap-2 text-sm text-foreground">
              {sheet.previousInstallations.map((row, index) => (
                <li key={index} className="flex flex-col gap-0.5">
                  <span className="wrap-break-word">
                    <span className="font-medium">{row.year}</span> · {row.description}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {INSTALLATION_SCOPE_LABELS[row.scope]} · {formatNumber(row.customers)}{" "}
                    {row.customers === 1 ? "customer" : "customers"} · {row.costLakhs} lakhs
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </CardContent>
    </Card>
  );
}

function Fact({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm wrap-break-word text-foreground">{children}</dd>
    </div>
  );
}
