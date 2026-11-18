import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { checkImport, commitImport, uploadImport, type UploadImportInput } from "./imports.api";
import type { ImportBatch, ImportCheck, ImportCommitResult } from "./imports.schemas";

const importKeys = { all: ["imports"] as const };

/**
 * MSTR-007 · The import's steps. A commit changes partners or a price list: the screen that
 * opened the dialog refreshes its own data from `onCommitted`, since only it knows which.
 */
export function useUploadImport(): UseMutationResult<ImportBatch, Error, UploadImportInput> {
  return useMutation({
    mutationKey: [...importKeys.all, "upload"],
    mutationFn: uploadImport,
    meta: { dataId: "MSTR-007" },
  });
}

export function useCheckImport(): UseMutationResult<
  ImportCheck,
  Error,
  Parameters<typeof checkImport>[0]
> {
  return useMutation({
    mutationKey: [...importKeys.all, "check"],
    mutationFn: checkImport,
    meta: { dataId: "MSTR-007" },
  });
}

export function useCommitImport(): UseMutationResult<
  ImportCommitResult,
  Error,
  Parameters<typeof commitImport>[0]
> {
  return useMutation({
    mutationKey: [...importKeys.all, "commit"],
    mutationFn: commitImport,
    meta: { dataId: "MSTR-007" },
  });
}
