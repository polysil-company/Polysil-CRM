"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { markReadLocally } from "@/features/notifications/lib/mark-read";

import { markNotificationsRead } from "./notifications.api";
import { notificationKeys, notificationListQueryOptions } from "./notifications.queries";
import type {
  MarkNotificationsReadRequest,
  MarkNotificationsReadResult,
  NotificationList,
} from "./notifications.schemas";

interface MarkReadContext {
  readonly previous: NotificationList | undefined;
}

/**
 * NOTIF-002. Updates the bell at once (optimistically), restores it if the request
 * fails, and refetches afterwards so the count matches the server.
 */
export function useMarkNotificationsRead(): UseMutationResult<
  MarkNotificationsReadResult,
  Error,
  MarkNotificationsReadRequest,
  MarkReadContext
> {
  const queryClient = useQueryClient();
  const { queryKey } = notificationListQueryOptions();

  return useMutation({
    mutationKey: [...notificationKeys.all, "read"],
    mutationFn: (request: MarkNotificationsReadRequest) => markNotificationsRead(request),
    meta: { dataId: "NOTIF-002" },
    onMutate: async (request): Promise<MarkReadContext> => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData(queryKey);
      if (previous !== undefined) {
        queryClient.setQueryData(
          queryKey,
          markReadLocally(previous, request, new Date().toISOString()),
        );
      }
      return { previous };
    },
    onError: (_error, _request, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: notificationKeys.all });
    },
  });
}
