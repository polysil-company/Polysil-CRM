import { z } from "zod";

/**
 * BOT-001, BOT-002 · The in-app assistant (FS-045, `in-app-assistant.md`, generated
 * `assistant.md`): a search box, not a chatbot. Actions the user may take, and records found
 * by number, mobile or name. `screen` is a stable key the frontend maps to its own route.
 */

export const ASSISTANT_SCREENS = [
  "leads.new",
  "leads.list",
  "leads.detail",
  "leads.duplicates",
  "leads.qr_codes",
  "customers.list",
  "customers.detail",
  "campaigns.list",
  "campaigns.new",
  "quotations.new",
  "quotations.list",
  "quotations.detail",
  "approvals.queue",
  "orders.new",
  "orders.list",
  "orders.detail",
  "dispatch.list",
  "payments.new",
  "payments.list",
  "complaints.new",
  "complaints.list",
  "complaints.detail",
  "tasks.new",
  "tasks.planner",
  "subsidy.applications",
  "subsidy.applications.new",
  "schemes.list",
  "rewards.list",
  "marketing.orders.new",
  "stock.list",
  "targets.list",
  "reports.list",
  "tracking.map",
  "messages.list",
  "partners.list",
  "users.list",
  "users.new",
  "products.list",
  "pricing.lists",
  "settings.holidays",
  "settings.company",
  "settings.lookups",
] as const;
export type AssistantScreen = (typeof ASSISTANT_SCREENS)[number];

export const RECORD_KINDS = ["lead", "customer", "quotation", "sales_order", "complaint"] as const;
export type RecordKind = (typeof RECORD_KINDS)[number];

/** Records are searched from this many characters. */
export const RECORD_SEARCH_MIN = 3;
/** The backend refuses a longer `q`. */
export const ASSISTANT_QUERY_MAX = 100;
export const ASSISTANT_LIMIT = 8;

/** A key the frontend doesn't know yet still parses, and is left out of the menu. */
const screenSchema = z
  .string()
  .transform((value) => ASSISTANT_SCREENS.find((screen) => screen === value) ?? null);

const actionWireSchema = z.object({
  key: z.string().min(1),
  title: z.string(),
  hint: z.string(),
  screen: z.string(),
  module: z.string(),
});
export type AssistantActionWire = z.input<typeof actionWireSchema>;

const actionSchema = actionWireSchema.extend({ screen: screenSchema });

const recordWireSchema = z.object({
  kind: z.string(),
  id: z.string().min(1),
  label: z.string(),
  screen: z.string(),
});
export type AssistantRecordWire = z.input<typeof recordWireSchema>;

const recordSchema = recordWireSchema.extend({
  kind: z.string().transform((value) => RECORD_KINDS.find((kind) => kind === value) ?? null),
  screen: screenSchema,
});

export const assistantAnswerSchema = z
  .object({ data: z.object({ actions: z.array(actionSchema), records: z.array(recordSchema) }) })
  .transform(({ data }) => ({
    actions: data.actions.flatMap((action) =>
      action.screen === null ? [] : [{ ...action, screen: action.screen }],
    ),
    records: data.records.flatMap((record) =>
      record.screen === null || record.kind === null
        ? []
        : [{ ...record, screen: record.screen, kind: record.kind }],
    ),
  }));
export type AssistantAnswer = z.output<typeof assistantAnswerSchema>;
export type AssistantAction = AssistantAnswer["actions"][number];
export type AssistantRecord = AssistantAnswer["records"][number];

export const assistantActionsSchema = z
  .object({ data: z.array(actionSchema) })
  .transform(({ data }) =>
    data.flatMap((action) =>
      action.screen === null ? [] : [{ ...action, screen: action.screen }],
    ),
  );
