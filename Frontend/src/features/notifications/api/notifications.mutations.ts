"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { markReadLocally, unreadAfterMarking } from "@/features/notifications/lib/mark-read";

import { markNotificationsRead } from "./notifications.api";
import {
  notificationCountQueryOptions,
  notificationKeys,
  notificationListQueryOptions,
} from "./notifications.queries";
import type {
  MarkNotificationsReadRequest,
  MarkNotificationsReadResult,
  NotificationList,
} from "./notifications.schemas";

interface MarkReadContext {
  readonly previousList: NotificationList | undefined;
  readonly previousCount: number | undefined;
}

/**
 * NOTIF-002. Updates the list and the badge at once (optimistically), restores both if the
 * request fails, takes the backend's new count when it answers, and refetches afterwards.
 */
export function useMarkNotificationsRead(): UseMutationResult<
  MarkNotificationsReadResult,
  Error,
  MarkNotificationsReadRequest,
  MarkReadContext
> {
  const queryClient = useQueryClient();
  const listKey = notificationListQueryOptions().queryKey;
  const countKey = notificationCountQueryOptions().queryKey;

  return useMutation({
    mutationKey: [...notificationKeys.all, "read"],
    mutationFn: (request: MarkNotificationsReadRequest) => markNotificationsRead(request),
    meta: { dataId: "NOTIF-002" },
    onMutate: async (request): Promise<MarkReadContext> => {
      await queryClient.cancelQueries({ queryKey: notificationKeys.all });
      const previousList = queryClient.getQueryData(listKey);
      const previousCount = queryClient.getQueryData(countKey);
      if (previousList !== undefined) {
        queryClient.setQueryData(
          listKey,
          markReadLocally(previousList, request, new Date().toISOString()),
        );
      }
      if (previousCount !== undefined) {
        queryClient.setQueryData(
          countKey,
          unreadAfterMarking(previousCount, previousList, request),
        );
      }
      return { previousList, previousCount };
    },
    onSuccess: (result) => {
      queryClient.setQueryData(countKey, result.unreadCount);
    },
    onError: (_error, _request, context) => {
      if (context?.previousList !== undefined) {
        queryClient.setQueryData(listKey, context.previousList);
      }
      if (context?.previousCount !== undefined) {
        queryClient.setQueryData(countKey, context.previousCount);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: notificationKeys.all });
    },
  });
}
