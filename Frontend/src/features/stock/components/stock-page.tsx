"use client";

import { Add01Icon } from "@hugeicons/core-free-icons";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import { useState } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCan } from "@/features/session/hooks/use-session";

import { RecordStockForm } from "./record-stock-form";
import { StockLedger } from "./stock-ledger";
import { StockList } from "./stock-list";
import { WarehousesAdmin } from "./warehouses-admin";

const TABS = ["stock", "ledger", "warehouses"] as const;
type Tab = (typeof TABS)[number];

const TAB_LABELS: Readonly<Record<Tab, string>> = {
  stock: "Stock",
  ledger: "Ledger",
  warehouses: "Warehouses",
};

/**
 * MSTR-014 … MSTR-016 · Stock: what each warehouse holds and what open orders have committed,
 * the ledger of every movement, and (for Admin) the warehouses. Dispatch records stock received
 * and corrections. The tab is in the URL.
 */
export function StockPage(): React.JSX.Element {
  const canRecord = useCan("stock", "create");
  const canEdit = useCan("stock", "edit");
  const tabs: readonly Tab[] = TABS.filter((tab) => tab !== "warehouses" || canEdit);
  const [chosen, setTab] = useQueryState("tab", parseAsStringLiteral(TABS).withDefault("stock"));
  const tab: Tab = tabs.includes(chosen) ? chosen : "stock";
  const [recording, setRecording] = useState(false);

  return (
    <>
      <Tabs
        value={tab}
        onValueChange={(next: Tab) => {
          void setTab(next === "stock" ? null : next);
        }}
        className="flex flex-col gap-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList aria-label="Stock" className="scrollbar-none overflow-x-auto">
            {tabs.map((value) => (
              <TabsTrigger key={value} value={value}>
                {TAB_LABELS[value]}
              </TabsTrigger>
            ))}
          </TabsList>
          {canRecord && tab !== "warehouses" ? (
            <Button
              onClick={() => {
                setRecording(true);
              }}
            >
              <Icon icon={Add01Icon} />
              Record stock
            </Button>
          ) : null}
        </div>
        <TabsContent value="stock">
          <StockList />
        </TabsContent>
        <TabsContent value="ledger">
          <StockLedger />
        </TabsContent>
        {tabs.includes("warehouses") ? (
          <TabsContent value="warehouses">
            <WarehousesAdmin />
          </TabsContent>
        ) : null}
      </Tabs>
      <Dialog open={recording} onOpenChange={setRecording}>
        <DialogContent size="lg">
          {recording ? (
            <RecordStockForm
              onClose={() => {
                setRecording(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
