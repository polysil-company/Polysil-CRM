import { z } from "zod";

/**
 * ADMN-008 · The org chart (FS-080, `GET /users/org-chart`): who reports to whom. Managers are
 * worked out by the backend from office and role, so the chart follows any change at once.
 * Contract: `backend/docs/api/users.md`.
 */

const id = z.string().min(1);
const roleRefSchema = z.object({ code: z.string().min(1), name: z.string() });
const orgUnitRefSchema = z.object({ id, name: z.string() });

const personWireSchema = z.object({
  id,
  full_name: z.string(),
  role: roleRefSchema,
  /** 1 field officer up to 5 head office. */
  level: z.number().int(),
  org_unit: orgUnitRefSchema,
});

const nodeWireSchema = personWireSchema.extend({
  /** Who this person reports to, sorted by name: draw under the first, "also reports to" the rest. */
  manager_ids: z.array(id),
  direct_reports: z.number().int(),
  /** Everyone below, at any depth, each counted once. */
  team_size: z.number().int(),
});

const orgChartWireSchema = z.object({
  /** Null in the company view. */
  subject: personWireSchema.nullable(),
  /** The chain above the subject, nearest first; a step may hold two people. */
  managers: z.array(z.array(personWireSchema)),
  people: z.array(nodeWireSchema),
  /** Named in some `manager_ids` but nowhere else, such as a second District Manager. */
  co_managers: z.array(personWireSchema),
  totals: z.object({
    people: z.number().int(),
    by_role: z.array(z.object({ role: roleRefSchema, count: z.number().int() })),
  }),
  /** Company view only: staff on the System office, who can't be placed. */
  unplaced: z.array(personWireSchema).default([]),
});

export interface OrgPerson {
  readonly id: string;
  readonly name: string;
  readonly roleCode: string;
  readonly roleName: string;
  readonly level: number;
  readonly office: string;
}

export interface OrgNode extends OrgPerson {
  readonly managerIds: readonly string[];
  readonly directReports: number;
  readonly teamSize: number;
}

export interface OrgChart {
  readonly subject: OrgPerson | null;
  readonly managers: readonly (readonly OrgPerson[])[];
  readonly people: readonly OrgNode[];
  readonly coManagers: readonly OrgPerson[];
  readonly total: number;
  readonly byRole: readonly { readonly roleName: string; readonly count: number }[];
  readonly unplaced: readonly OrgPerson[];
}

function toPerson(wire: z.output<typeof personWireSchema>): OrgPerson {
  return {
    id: wire.id,
    name: wire.full_name,
    roleCode: wire.role.code,
    roleName: wire.role.name,
    level: wire.level,
    office: wire.org_unit.name,
  };
}

export const orgChartSchema = z
  .object({ data: orgChartWireSchema })
  .transform(({ data }): OrgChart => ({
    subject: data.subject === null ? null : toPerson(data.subject),
    managers: data.managers.map((step) => step.map(toPerson)),
    people: data.people.map((node) => ({
      ...toPerson(node),
      managerIds: node.manager_ids,
      directReports: node.direct_reports,
      teamSize: node.team_size,
    })),
    coManagers: data.co_managers.map(toPerson),
    total: data.totals.people,
    byRole: data.totals.by_role.map((item) => ({ roleName: item.role.name, count: item.count })),
    unplaced: data.unplaced.map(toPerson),
  }));

/** Whose picture: mine (neither set), someone below me, or the whole company. */
export interface OrgChartParams {
  readonly userId: string | null;
  readonly company: boolean;
}

export type OrgChartWire = z.input<typeof orgChartWireSchema>;
