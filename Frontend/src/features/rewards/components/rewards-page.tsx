"use client";

import { parseAsStringLiteral, useQueryState } from "nuqs";
import type * as React from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";

import { GiftDesk } from "./gift-desk";
import { GiftsPanel } from "./gifts-panel";
import { PointsPanel } from "./points-panel";
import { RewardSettingsPanel } from "./reward-settings-panel";
import { RulesPanel } from "./rules-panel";

const TABS = ["points", "gifts", "desk", "rules", "settings"] as const;
type Tab = (typeof TABS)[number];

const TAB_LABELS: Readonly<Record<Tab, string>> = {
  points: "Points",
  gifts: "Gifts",
  desk: "Gift desk",
  rules: "Earning rules",
  settings: "Point value",
};

/**
 * RWD-001 … RWD-003 · Reward points. Everyone with rewards sees their points and the gifts; a
 * dealer asks for a gift. Staff read the earning rules and the point value; Admin changes them
 * and the gifts (rewards.edit), and works the gift desk (rewards.approve). The tab is in the URL.
 */
export function RewardsPage(): React.JSX.Element {
  const isStaff = useIsStaff();
  const canApprove = useCan("rewards", "approve");
  const canEdit = useCan("rewards", "edit");
  const shown: readonly Tab[] = TABS.filter((tab) => {
    if (tab === "desk") return isStaff && canApprove;
    if (tab === "rules" || tab === "settings") return isStaff;
    return true;
  });
  const [chosen, setTab] = useQueryState("tab", parseAsStringLiteral(TABS).withDefault("points"));
  // A tab this person can't see (a shared link) opens on their points.
  const tab: Tab = shown.includes(chosen) ? chosen : "points";

  return (
    <Tabs
      value={tab}
      onValueChange={(next: Tab) => {
        void setTab(next === "points" ? null : next);
      }}
      className="flex flex-col gap-4"
    >
      <TabsList aria-label="Rewards" className="scrollbar-none self-start overflow-x-auto">
        {shown.map((value) => (
          <TabsTrigger key={value} value={value}>
            {TAB_LABELS[value]}
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent value="points">
        <PointsPanel />
      </TabsContent>
      <TabsContent value="gifts">
        <GiftsPanel />
      </TabsContent>
      {shown.includes("desk") ? (
        <TabsContent value="desk">
          <GiftDesk />
        </TabsContent>
      ) : null}
      {shown.includes("rules") ? (
        <TabsContent value="rules">
          <RulesPanel canEdit={canEdit} />
        </TabsContent>
      ) : null}
      {shown.includes("settings") ? (
        <TabsContent value="settings">
          <RewardSettingsPanel canEdit={canEdit} />
        </TabsContent>
      ) : null}
    </Tabs>
  );
}
