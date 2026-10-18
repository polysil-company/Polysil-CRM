"use client";

import { parseAsStringLiteral, useQueryState } from "nuqs";
import type * as React from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LOOKUP_LISTS } from "@/features/lookups/api/lookups.schemas";
import { useCan } from "@/features/session/hooks/use-session";
import { WarrantyTermsPanel } from "@/features/warranty/components/warranty-terms-panel";

import { HolidaysPanel } from "./holidays-panel";
import { LIST_COPY, LookupListPanel } from "./lookup-list-panel";
import { OfficesPanel } from "./offices-panel";
import { ScoringPanel } from "./scoring-panel";
import { TerritoriesPanel } from "./territories-panel";

/** The tabs: each admin list, the lead score's settings, the offices, then the territories. */
export const MASTER_TABS = [
  ...LOOKUP_LISTS,
  "scoring",
  "offices",
  "territories",
  "warranty",
  "holidays",
] as const;
export type MasterTab = (typeof MASTER_TABS)[number];

const DEFAULT_TAB: MasterTab = "lead-sources";

function tabLabel(tab: MasterTab): string {
  if (tab === "scoring") return "Lead scoring";
  if (tab === "offices") return "Offices";
  if (tab === "territories") return "Territories";
  if (tab === "warranty") return "Warranty periods";
  if (tab === "holidays") return "Holidays";
  return LIST_COPY[tab].title;
}

/**
 * MSTR-001 · Admin → Masters: the lists behind the pickers (MSTR-009), the lead score's
 * settings (MSTR-010), the offices (MSTR-011), the territories (MSTR-012), the warranty periods (MSTR-017) and the holidays (MSTR-019), one tab each, the open tab kept in the URL. Everyone who sees Masters
 * reads them; those who may edit masters add rows, switch them on or off, and retune the score.
 */
export function Masters(): React.JSX.Element {
  const canEdit = useCan("masters", "edit");
  const [tab, setTab] = useQueryState(
    "tab",
    parseAsStringLiteral(MASTER_TABS).withDefault(DEFAULT_TAB),
  );

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-prose text-sm text-muted-foreground">
        The lists every form picks from, how a lead is scored, the office tree, the territories, the
        warranty periods and the holidays. A list row is never deleted: one no longer wanted is
        switched off, so records that use it keep it.
        {canEdit ? "" : " Only administrators of masters change them."}
      </p>
      <Tabs
        value={tab}
        onValueChange={(next: MasterTab) => {
          void setTab(next === DEFAULT_TAB ? null : next);
        }}
      >
        <TabsList aria-label="Master" className="scrollbar-none overflow-x-auto">
          {MASTER_TABS.map((item) => (
            <TabsTrigger key={item} value={item}>
              {tabLabel(item)}
            </TabsTrigger>
          ))}
        </TabsList>
        {LOOKUP_LISTS.map((list) => (
          <TabsContent key={list} value={list}>
            <LookupListPanel list={list} canEdit={canEdit} />
          </TabsContent>
        ))}
        <TabsContent value="scoring">
          <ScoringPanel canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="offices">
          <OfficesPanel canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="territories">
          <TerritoriesPanel canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="warranty">
          <WarrantyTermsPanel canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="holidays">
          <HolidaysPanel canEdit={canEdit} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
