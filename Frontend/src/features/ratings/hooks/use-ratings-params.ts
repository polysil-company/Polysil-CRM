"use client";

import { parseAsStringLiteral, useQueryStates } from "nuqs";

import {
  RATING_SUMMARY_GROUPS,
  RATING_TARGETS,
  type RatingSummaryGroup,
  type RatingTarget,
} from "@/features/ratings/api/ratings.schemas";

export const RATINGS_TABS = ["list", "summary"] as const;
export type RatingsTab = (typeof RATINGS_TABS)[number];

export const RATING_SCORE_FILTERS = ["all", "low"] as const;
export type RatingScoreFilter = (typeof RATING_SCORE_FILTERS)[number];

/** RATE-002, RATE-003 · The ratings page's place in the URL: tab, kind, low only, grouping. */
export function useRatingsParams(): {
  tab: RatingsTab;
  target: RatingTarget | null;
  score: RatingScoreFilter;
  group: RatingSummaryGroup;
  set: (patch: {
    tab?: RatingsTab;
    target?: RatingTarget | null;
    score?: RatingScoreFilter;
    group?: RatingSummaryGroup;
  }) => void;
} {
  const [values, setValues] = useQueryStates({
    tab: parseAsStringLiteral(RATINGS_TABS).withDefault("list"),
    target: parseAsStringLiteral(RATING_TARGETS),
    score: parseAsStringLiteral(RATING_SCORE_FILTERS).withDefault("all"),
    group: parseAsStringLiteral(RATING_SUMMARY_GROUPS).withDefault("partner"),
  });
  return {
    tab: values.tab,
    target: values.target,
    score: values.score,
    group: values.group,
    set: (patch) => {
      void setValues({
        ...(patch.tab === undefined ? {} : { tab: patch.tab === "list" ? null : patch.tab }),
        ...(patch.target === undefined ? {} : { target: patch.target }),
        ...(patch.score === undefined ? {} : { score: patch.score === "all" ? null : patch.score }),
        ...(patch.group === undefined
          ? {}
          : { group: patch.group === "partner" ? null : patch.group }),
      });
    },
  };
}
