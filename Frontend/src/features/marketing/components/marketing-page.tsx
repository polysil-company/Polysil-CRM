"use client";

import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import type * as React from "react";

import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ORDER_VIEWS, type OrderView } from "@/features/marketing/api/marketing.schemas";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";

import { CatalogueAdmin } from "./catalogue-admin";
import { MarketingOrderDialog } from "./marketing-order-dialog";
import { MarketingOrders } from "./marketing-orders";
import { OrderMaterial } from "./order-material";

const TABS = ["order", "orders", "catalogue"] as const;
type Tab = (typeof TABS)[number];

const TAB_LABELS: Readonly<Record<Tab, string>> = {
  order: "Order material",
  orders: "Orders",
  catalogue: "Catalogue",
};

/**
 * MKT-002 … MKT-004 · Marketing material. Anyone who may order picks from the catalogue; Orders
 * shows theirs, the ones to approve (District Managers) and to send (the marketing team), and
 * all of them for staff. The marketing team keeps the catalogue. The tab, the list's view and the
 * open order are in the URL, so a link opens the same order.
 */
export function MarketingPage(): React.JSX.Element {
  const staff = useIsStaff();
  const canOrder = useCan("marketing_material", "create");
  const canApprove = useCan("marketing_material", "approve");
  const canEdit = useCan("marketing_material", "edit");

  const tabs: readonly Tab[] = TABS.filter((tab) => {
    if (tab === "order") return canOrder;
    if (tab === "catalogue") return staff && canEdit;
    return true;
  });
  const views: readonly OrderView[] = ORDER_VIEWS.filter((view) => {
    if (view === "awaiting") return staff && canApprove;
    if (view === "dispatch") return staff && canEdit;
    if (view === "all") return staff;
    return true;
  });
  const fallback: Tab = tabs[0] ?? "orders";
  const [chosenTab, setTab] = useQueryState("tab", parseAsStringLiteral(TABS));
  const tab: Tab = chosenTab !== null && tabs.includes(chosenTab) ? chosenTab : fallback;
  const [chosenView, setView] = useQueryState("view", parseAsStringLiteral(ORDER_VIEWS));
  const firstView: OrderView = views.includes("awaiting") ? "awaiting" : "mine";
  const view: OrderView =
    chosenView !== null && views.includes(chosenView) ? chosenView : firstView;
  const [orderId, setOrderId] = useQueryState("order", parseAsString);

  return (
    <>
      <Tabs
        value={tab}
        onValueChange={(next: Tab) => {
          void setTab(next === fallback ? null : next);
        }}
        className="flex flex-col gap-4"
      >
        <TabsList
          aria-label="Marketing material"
          className="scrollbar-none self-start overflow-x-auto"
        >
          {tabs.map((value) => (
            <TabsTrigger key={value} value={value}>
              {TAB_LABELS[value]}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.includes("order") ? (
          <TabsContent value="order">
            <OrderMaterial
              onPlaced={(order) => {
                void setTab("orders");
                void setView("mine");
                void setOrderId(order.id);
              }}
            />
          </TabsContent>
        ) : null}
        <TabsContent value="orders">
          <MarketingOrders
            views={views}
            view={view}
            onView={(next) => {
              void setView(next === firstView ? null : next);
            }}
            onOpen={(id) => {
              void setOrderId(id);
            }}
          />
        </TabsContent>
        {tabs.includes("catalogue") ? (
          <TabsContent value="catalogue">
            <CatalogueAdmin />
          </TabsContent>
        ) : null}
      </Tabs>

      <Dialog
        open={orderId !== null}
        onOpenChange={(open) => {
          if (!open) void setOrderId(null);
        }}
      >
        <DialogContent size="lg">
          {orderId === null ? null : (
            <MarketingOrderDialog
              key={orderId}
              orderId={orderId}
              onClose={() => {
                void setOrderId(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
