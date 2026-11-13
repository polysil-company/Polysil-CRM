/** BOT-002 · Headings for the help page, by the module the backend names on each action. */
const MODULE_LABELS: Readonly<Record<string, string>> = {
  leads: "Leads and customers",
  campaigns: "Campaigns",
  quotations: "Quotations",
  sales_orders: "Sales orders and approvals",
  dispatch: "Dispatch",
  payments: "Payments",
  complaints: "Complaints",
  tasks: "Tasks",
  subsidy: "Subsidy",
  schemes: "Schemes",
  rewards: "Rewards",
  marketing_material: "Marketing material",
  marketing: "Marketing",
  stock: "Stock",
  targets: "Targets",
  reports: "Reports",
  tracking: "Field tracking",
  partners: "Dealers and distributors",
  users: "Users",
  products: "Products",
  pricing: "Pricing",
  masters: "Settings and masters",
  general: "General",
};

/** A module's heading; one the frontend doesn't know yet reads from its code. */
export function moduleLabel(module: string): string {
  const known = MODULE_LABELS[module];
  if (known !== undefined) return known;
  const words = module.replace(/[_.]+/g, " ").trim();
  return words === "" ? "Other" : words.charAt(0).toUpperCase() + words.slice(1);
}

/** Actions grouped by module, in the order the backend first names each module. */
export function groupByModule<T extends { module: string }>(
  actions: readonly T[],
): { module: string; actions: T[] }[] {
  const groups = new Map<string, T[]>();
  for (const action of actions) {
    const group = groups.get(action.module);
    if (group === undefined) groups.set(action.module, [action]);
    else group.push(action);
  }
  return [...groups].map(([module, items]) => ({ module, actions: items }));
}
