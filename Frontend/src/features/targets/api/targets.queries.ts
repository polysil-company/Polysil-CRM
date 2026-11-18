import { queryOptions } from "@tanstack/react-query";

import { getAchievement, getPersonTargets } from "./targets.api";

export const targetKeys = {
  all: ["targets"] as const,
  achievement: (month: string) => [...targetKeys.all, "achievement", month] as const,
  person: (userId: string, month: string) => [...targetKeys.all, "person", userId, month] as const,
};

/** TGT-001 · The month's achievement: live, so it refreshes when the page is looked at again. */
export function achievementQueryOptions(month: string) {
  return queryOptions({
    queryKey: targetKeys.achievement(month),
    queryFn: ({ signal }) => getAchievement(month, signal),
    meta: { dataId: "TGT-001" },
  });
}

/** TGT-002 · One person's targets for the month, with their history. */
export function personTargetsQueryOptions(userId: string, month: string) {
  return queryOptions({
    queryKey: targetKeys.person(userId, month),
    queryFn: ({ signal }) => getPersonTargets(userId, month, signal),
    meta: { dataId: "TGT-002" },
  });
}
