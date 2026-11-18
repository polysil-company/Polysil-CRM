"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { deleteDocument, uploadDocument } from "./documents.api";
import { documentKeys } from "./documents.queries";
import type { RecordDocument } from "./documents.schemas";

function useRefresh(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: documentKeys.all });
  };
}

/** DOC-002 · Attach a file to a record. */
export function useUploadDocument(): UseMutationResult<
  RecordDocument,
  Error,
  Parameters<typeof uploadDocument>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...documentKeys.all, "upload"],
    mutationFn: uploadDocument,
    meta: { dataId: "DOC-002" },
    onSuccess: refresh,
  });
}

/** DOC-003 · Remove a document; it stays on record, hidden from lists. */
export function useDeleteDocument(): UseMutationResult<
  void,
  Error,
  Parameters<typeof deleteDocument>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...documentKeys.all, "delete"],
    mutationFn: deleteDocument,
    meta: { dataId: "DOC-003" },
    onSuccess: refresh,
  });
}
